from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .database import connect, now_iso, new_id
from .agents.agent_registry import AgentRegistry
from .project_prompts import get_project_prompt, PROMPT_ROOT
from .capability_catalog import list_system_capabilities
from .context.runtime_environment import build_runtime_environment, format_runtime_environment
from .tools.tool_registry import ToolRegistry

router = APIRouter(prefix='/api/v1', tags=['Project Team Orchestration'])
WORKSPACE = Path(os.getenv('AGENT_WORKSPACE', str(Path.home() / 'AgentWorkspace'))).expanduser()
STATE = WORKSPACE / '.agent_state'
PLANS = STATE / 'project_team_plans.json'
GAPS = STATE / 'capability_gap_requests.json'
AGENTS = STATE / 'specialist_agents.json'
TOOLS = STATE / 'tools.json'
MAIN_CONFIG = STATE / 'main_agent_config.json'
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1').rstrip('/')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3:1.7b')


def _read(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    temp.replace(path)

def _persist_team_plan(conn, plan: dict[str, Any], proposal_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    """Persist a versioned Team Plan independently of Proposal/Project lifecycle."""
    if not proposal_id and not project_id:
        raise ValueError('A Team Plan must be associated with a Proposal or Project.')
    where, key = ('proposal_id=?', proposal_id) if proposal_id else ('project_id=?', project_id)
    previous = conn.execute(
        f'SELECT id,version FROM sys_team_plans WHERE {where} ORDER BY version DESC LIMIT 1', (key,)
    ).fetchone()
    version = max(int(plan.get('version', 1) or 1), (int(previous['version']) + 1) if previous else 1)
    plan = dict(plan)
    plan.update({'team_plan_id': plan.get('team_plan_id') or new_id(), 'proposal_id': proposal_id or plan.get('proposal_id'),
                 'project_id': project_id or plan.get('project_id'), 'version': version,
                 'created_at': plan.get('created_at') or now_iso(), 'updated_at': now_iso()})
    if previous:
        conn.execute("UPDATE sys_team_plans SET status='superseded',updated_at=? WHERE id=?", (now_iso(), previous['id']))
    conn.execute(
        'INSERT INTO sys_team_plans(id,proposal_id,project_id,version,status,plan_json,created_at,updated_at,approved_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (plan['team_plan_id'], plan.get('proposal_id'), plan.get('project_id'), version, plan.get('status','draft'),
         json.dumps(plan, ensure_ascii=False), plan['created_at'], plan['updated_at'], plan.get('approved_at')))
    return plan


def _latest_team_plan(conn, proposal_id: str | None = None, project_id: str | None = None):
    where, key = ('proposal_id=?', proposal_id) if proposal_id else ('project_id=?', project_id)
    row = conn.execute(f'SELECT plan_json FROM sys_team_plans WHERE {where} ORDER BY version DESC LIMIT 1', (key,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row['plan_json'])
    except (TypeError, json.JSONDecodeError):
        return None


class GapDecision(BaseModel):
    decision: str = Field(pattern='^(resolved|rejected|deferred)$')
    owner_note: str = ''


class PlannedWorkstream(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    objective: str = Field(default='', max_length=1200)
    required_capabilities: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    candidate_agent_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(default='', max_length=1600)
    confidence: float = Field(default=0.5, ge=0, le=1)


class PlannerOutput(BaseModel):
    project_summary: str = Field(min_length=1, max_length=3000)
    workstreams: list[PlannedWorkstream] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    questions_for_owner: list[str] = Field(default_factory=list, max_length=20)


def _main_model() -> str:
    config = _read(MAIN_CONFIG, {})
    return str(config.get('model') or OLLAMA_MODEL)


def _describe_planner_error(exc: Exception, model: str) -> str:
    """Return actionable, bounded diagnostics for Ollama planning failures."""
    details = f'{type(exc).__name__}: {str(exc).strip() or "no exception message"}'
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        body = (response.text or '').strip().replace('\\n', ' ')
        if len(body) > 1200:
            body = body[:1200] + '…'
        details = f'HTTP {response.status_code}; {details}'
        if body:
            details += f'; response={body}'
    elif isinstance(exc, httpx.TimeoutException):
        details += '; Ollama did not respond before the configured timeout'
    elif isinstance(exc, httpx.ConnectError):
        details += '; cannot connect to the Ollama OpenAI-compatible endpoint'
    return f'Model "{model}" at {OLLAMA_BASE_URL}: {details}'


async def _installed_models() -> list[str]:
    root = OLLAMA_BASE_URL.removesuffix('/v1')
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get(f'{root}/api/tags')
        response.raise_for_status()
    return [str(item.get('name')) for item in response.json().get('models', []) if item.get('name')]


def _tool_catalog() -> list[dict[str, Any]]:
    builtin = [
        {'tool_id': 'sqlite_query', 'function_name': 'sqlite_query', 'name': 'Read-only SQLite query', 'enabled': True, 'source': 'built-in'},
        {'tool_id': 'workspace_file_management', 'function_name': 'workspace_file_management', 'name': 'Workspace file read/list', 'enabled': True, 'source': 'built-in'},
        {'tool_id': 'sqlite_modify', 'function_name': 'sqlite_modify', 'name': 'SQLite modification', 'enabled': True, 'source': 'built-in', 'requires_explicit_permission': True},
        {'tool_id': 'workspace_modify', 'function_name': 'workspace_modify', 'name': 'Workspace file modification', 'enabled': True, 'source': 'built-in', 'requires_explicit_permission': True},
    ]
    configured = []
    for item in ToolRegistry(TOOLS).list_tools():
        configured.append({
            'tool_id': item.get('tool_id'), 'function_name': item.get('function_name'),
            'name': item.get('name'), 'description': item.get('description', ''),
            'enabled': bool(item.get('enabled')), 'source': 'configured',
        })
    return builtin + configured


def _normalise_gap(project_id: str, gap_type: str, subject: str, reason: str, recommendation: str) -> dict[str, Any]:
    return {
        'gap_id': new_id(), 'project_id': project_id, 'gap_type': gap_type,
        'required_capability': subject, 'reason': reason, 'recommendation': recommendation,
        'status': 'open', 'created_at': now_iso(), 'owner_note': '',
    }


async def _call_planner(model: str, payload: dict[str, Any], runtime_environment: dict[str, Any] | None = None) -> PlannerOutput:
    system = (format_runtime_environment(runtime_environment) + "\n\n" if runtime_environment else "") + '''You are the Main Agent acting as a project team planning analyst. Produce a proposed plan only.
Return exactly one JSON object with keys: project_summary, workstreams, risks, assumptions, questions_for_owner.
Each workstream must contain: name, objective, required_capabilities, required_tools, candidate_agent_ids, rationale, confidence.
For software/application/platform/system projects, include a distinct QA/testing workstream unless testing is explicitly out of scope. QA is a first-class delivery responsibility, not an optional afterthought.
Use ONLY capability IDs, tool IDs/function names, and agent IDs present in the supplied catalogs. Never invent an Agent, Tool, capability, model, permission, or availability claim. candidate_agent_ids may contain multiple ranked candidates. required_tools must be genuinely necessary for the workstream; do not request tools speculatively. If no registered Specialist can cover the work, leave candidate_agent_ids empty and explain the gap. Distinguish assumptions from confirmed project facts. Do not authorize execution or create tasks.'''
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        response = await client.post(
            f'{OLLAMA_BASE_URL}/chat/completions',
            headers={'Authorization': 'Bearer ollama'},
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
                ],
                'stream': False,
                'response_format': {'type': 'json_object'},
                'options': {'temperature': 0.1},
            },
        )
        response.raise_for_status()
    body = response.json()
    content = body.get('choices', [{}])[0].get('message', {}).get('content')
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Main Agent returned an empty planning response.')
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f'Main Agent returned invalid JSON: {exc}') from exc
    return PlannerOutput.model_validate(parsed)


@router.post('/projects/{project_id}/team-plan/analyze')
async def analyze_team_plan(project_id: str):
    with connect() as conn:
        project_row = conn.execute('SELECT * FROM sys_projects WHERE id=?', (project_id,)).fetchone()
        if not project_row:
            raise HTTPException(404, 'Project not found')
        tasks = [dict(row) for row in conn.execute(
            'SELECT id,name,description,completion_criteria FROM sys_tasks WHERE project_id=? ORDER BY created_at',
            (project_id,),
        ).fetchall()]
    project = dict(project_row)
    try:
        prompt_record = get_project_prompt(project_id)
        prompt_status = prompt_record.get('status', 'missing')
        active_version = prompt_record.get('active_version')
        # get_project_prompt() intentionally returns a pending draft for the editor.
        # Planning must consume only the Product Owner-approved active P4 version.
        prompt = ''
        if active_version:
            active_path = PROMPT_ROOT / project_id / 'versions' / f'v{int(active_version):04d}.md'
            if active_path.is_file():
                prompt = active_path.read_text(encoding='utf-8')
    except Exception:
        prompt, prompt_status, active_version = '', 'missing', None

    agent_registry = AgentRegistry(config_path=AGENTS)
    all_agents = agent_registry.list_agents()
    enabled_agents = [agent for agent in all_agents if agent.get('enabled')]
    capabilities = list_system_capabilities()
    tools = _tool_catalog()
    model = _main_model()
    try:
        installed_models = await _installed_models()
    except Exception as exc:
        raise HTTPException(502, f'Cannot verify installed Ollama models: {exc}') from exc
    if model not in installed_models:
        raise HTTPException(409, f'Main Agent model "{model}" is not installed in Ollama. Select an installed model before planning.')

    planner_input = {
        'project': {
            'project_id': project_id, 'name': project.get('name'),
            'objective': project.get('objective'), 'description': project.get('description'),
            'priority': project.get('priority'), 'baseline_due_date': project.get('baseline_due_date'),
            'project_prompt': prompt, 'project_prompt_status': prompt_status,
            'active_prompt_version': active_version,
        },
        'existing_tasks': tasks,
        'specialist_agents': [{
            'agent_id': a['agent_id'], 'display_name': a['display_name'],
            'capabilities': a.get('capabilities', []), 'allowed_task_types': a.get('allowed_task_types', []),
            'model': a.get('model') or None, 'enabled': a.get('enabled', False),
            'allowed_tools': a.get('allowed_tools', []), 'description': a.get('description', ''),
        } for a in enabled_agents],
        'system_capabilities': capabilities,
        'registered_tools': tools,
        'installed_ollama_models': installed_models,
        'constraints': [
            'Planning only. Do not create tasks or dispatch Agents.',
            'Only enabled Specialist Agents may be proposed.',
            'A model and every requested Tool must be installed/enabled and permission-checked.',
            'The Product Owner must review and approve this draft.',
        ],
    }
    planner_environment = build_runtime_environment(
        agent_id="team_planner",
        model=model,
        # The planner receives a reference catalog in its input, not callable tools.
        available_tools=[],
        allowed_tools=[],
        workspace_root=WORKSPACE,
        project_root=WORKSPACE,
        read_enabled=True,
        write_enabled=False,
        ollama_base_url=OLLAMA_BASE_URL,
    )
    try:
        planned = await _call_planner(model, planner_input, planner_environment)
    except httpx.HTTPError as exc:
        detail = _describe_planner_error(exc, model)
        raise HTTPException(502, f'Main Agent planning request failed. {detail}') from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(502, f'Main Agent planning output could not be validated: {exc}') from exc

    agent_by_id = {a['agent_id']: a for a in enabled_agents}
    capability_by_id = {c['capability_id']: c for c in capabilities}
    tool_by_key = {str(key): tool for tool in tools for key in (tool.get('tool_id'), tool.get('function_name')) if key}
    gaps: list[dict[str, Any]] = []
    workstreams: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    proposed_team: dict[str, dict[str, Any]] = {}

    for stream in planned.workstreams:
        stream_caps, stream_tools, candidate_details = [], [], []
        for cap_id in stream.required_capabilities:
            cap = capability_by_id.get(cap_id)
            if not cap:
                gaps.append(_normalise_gap(project_id, 'unknown_capability', cap_id,
                    f'Main Agent requested capability "{cap_id}", which is not in the system capability catalog.',
                    'Product Owner should review the requirement and configure or implement the capability.'))
                stream_caps.append({'capability_id': cap_id, 'status': 'unknown'})
            else:
                stream_caps.append({'capability_id': cap_id, 'name': cap['name'], 'available': bool(cap.get('available')), 'status': cap.get('status')})
                if not cap.get('available'):
                    gaps.append(_normalise_gap(project_id, 'capability_unavailable', cap_id,
                        f'{cap["name"]} is registered but unavailable ({cap.get("status")}).',
                        'Enable/configure the capability or revise the proposed workstream.'))

        for tool_key in stream.required_tools:
            tool = tool_by_key.get(tool_key)
            if not tool:
                gaps.append(_normalise_gap(project_id, 'tool_missing', tool_key,
                    f'Required Tool "{tool_key}" is not registered.',
                    'Register and enable the required Tool, or revise the workstream.'))
                stream_tools.append({'tool': tool_key, 'status': 'missing'})
            else:
                stream_tools.append({'tool_id': tool.get('tool_id'), 'function_name': tool.get('function_name'), 'name': tool.get('name'), 'enabled': tool.get('enabled'), 'status': 'available' if tool.get('enabled') else 'disabled'})
                if not tool.get('enabled'):
                    gaps.append(_normalise_gap(project_id, 'tool_disabled', tool_key,
                        f'Required Tool "{tool.get("name")}" is registered but disabled.',
                        'Enable the Tool in Tool Management or revise the workstream.'))

        for agent_id in stream.candidate_agent_ids:
            agent = agent_by_id.get(agent_id)
            if not agent:
                gaps.append(_normalise_gap(project_id, 'agent_unavailable', agent_id,
                    f'Proposed Agent "{agent_id}" is not present in the enabled Specialist catalog.',
                    'Enable/configure an existing Specialist or choose a valid Agent.'))
                continue
            agent_model = agent.get('model') or ''
            model_ok = bool(agent_model and agent_model in installed_models)
            if not model_ok:
                gaps.append(_normalise_gap(project_id, 'agent_model_unavailable', agent_id,
                    f'{agent["display_name"]} has no configured model or its model is not installed ({agent_model or "not configured"}).',
                    'Assign an installed Ollama model in Agent Management.'))
            missing_permissions = []
            for tool_key in stream.required_tools:
                tool = tool_by_key.get(tool_key)
                if tool and tool.get('enabled') and tool_key not in agent.get('allowed_tools', []) and tool.get('tool_id') not in agent.get('allowed_tools', []) and tool.get('function_name') not in agent.get('allowed_tools', []):
                    missing_permissions.append(tool_key)
            if missing_permissions:
                gaps.append(_normalise_gap(project_id, 'agent_tool_permission', agent_id,
                    f'{agent["display_name"]} is not permitted to use required Tool(s): {", ".join(missing_permissions)}.',
                    'Review and explicitly grant the required Tool permissions in Agent Management.'))
            candidate_details.append({
                'agent_id': agent_id, 'agent_name': agent['display_name'], 'model': agent_model or None,
                'model_available': model_ok, 'allowed_tools': agent.get('allowed_tools', []),
                'missing_tool_permissions': missing_permissions,
                'status': 'ready' if model_ok and not missing_permissions else 'blocked',
            })
            proposed_team[agent_id] = candidate_details[-1]
        if not stream.candidate_agent_ids:
            gaps.append(_normalise_gap(project_id, 'agent_gap', stream.name,
                f'No enabled Specialist was proposed for workstream "{stream.name}".',
                'Configure an appropriate Specialist or revise the proposed scope.'))

        workstreams.append({
            'name': stream.name, 'objective': stream.objective,
            'required_capabilities': stream_caps, 'required_tools': stream_tools,
            'candidate_agents': candidate_details, 'rationale': stream.rationale,
            'confidence': stream.confidence,
        })
        matches.append({
            'required_capability': ', '.join(stream.required_capabilities) or stream.name,
            'candidates': candidate_details, 'status': 'matched' if any(a['status'] == 'ready' for a in candidate_details) else 'needs_review',
        })

    plan = {
        'project_id': project_id, 'project_name': project.get('name'), 'version': 1,
        'status': 'draft', 'analysis_method': 'Main Agent LLM planning with deterministic registry, model, Tool and permission validation',
        'model_used': model, 'project_summary': planned.project_summary,
        'source_summary': {'objective': project.get('objective', ''), 'task_count': len(tasks), 'project_prompt_available': bool(prompt), 'project_prompt_status': prompt_status, 'active_prompt_version': active_version},
        'workstreams': workstreams, 'required_capabilities': sorted({c for w in planned.workstreams for c in w.required_capabilities}),
        'matches': matches, 'capability_gaps': gaps, 'proposed_team': list(proposed_team.values()),
        'risks': planned.risks, 'assumptions': planned.assumptions, 'questions_for_owner': planned.questions_for_owner,
        'created_at': now_iso(), 'updated_at': now_iso(),
    }
    all_plans = _read(PLANS, {})
    previous = all_plans.get(project_id, {})
    plan['version'] = int(previous.get('version', 0)) + 1
    with connect() as conn:
        proposal_link = conn.execute('SELECT proposal_id FROM sys_project_lifecycle WHERE project_id=?', (project_id,)).fetchone()
        plan = _persist_team_plan(conn, plan, proposal_id=proposal_link['proposal_id'] if proposal_link else None, project_id=project_id)
    all_plans[project_id] = plan
    _write(PLANS, all_plans)
    all_gaps = [g for g in _read(GAPS, []) if not (g.get('project_id') == project_id and g.get('status') in {'open', 'deferred'})]
    all_gaps.extend(gaps)
    _write(GAPS, all_gaps)
    return plan


@router.get('/projects/{project_id}/team-plan')
def get_team_plan(project_id: str):
    with connect() as conn:
        if not conn.execute('SELECT 1 FROM sys_projects WHERE id=?', (project_id,)).fetchone():
            raise HTTPException(404, 'Project not found')
    plan = _read(PLANS, {}).get(project_id)
    if not plan:
        with connect() as conn:
            plan = _latest_team_plan(conn, project_id=project_id)
    if not plan:
        raise HTTPException(404, 'Team plan has not been generated')
    return plan


@router.post('/projects/{project_id}/team-plan/approve')
def approve_team_plan(project_id: str):
    plans = _read(PLANS, {})
    with connect() as conn:
        plan = _latest_team_plan(conn, project_id=project_id)
    plan = plan or plans.get(project_id)
    if not plan:
        raise HTTPException(404, 'Team plan not found')
    unresolved = [g for g in _read(GAPS, []) if g.get('project_id') == project_id and g.get('status') != 'resolved']
    blocked_candidates = [a for a in plan.get('proposed_team', []) if a.get('status') != 'ready']
    if unresolved or blocked_candidates:
        raise HTTPException(409, 'Capability, Tool, model or permission gaps must be resolved before approving this team plan. Re-run analysis after configuration changes.')
    plan['status'] = 'owner_approved'
    plan['approved_at'] = now_iso()
    plan['updated_at'] = now_iso()
    with connect() as conn:
        proposal_link = conn.execute('SELECT proposal_id FROM sys_project_lifecycle WHERE project_id=?', (project_id,)).fetchone()
        plan = _persist_team_plan(conn, plan, proposal_id=proposal_link['proposal_id'] if proposal_link else None, project_id=project_id)
    plans[project_id] = plan
    _write(PLANS, plans)
    return plan


@router.get('/capability-requests')
def list_capability_requests(project_id: str | None = None):
    items = _read(GAPS, [])
    if project_id:
        items = [item for item in items if item.get('project_id') == project_id]
    return items


@router.patch('/capability-requests/{gap_id}')
def decide_capability_request(gap_id: str, payload: GapDecision):
    items = _read(GAPS, [])
    for item in items:
        if item.get('gap_id') == gap_id:
            item['status'] = payload.decision
            item['owner_note'] = payload.owner_note
            item['decided_at'] = now_iso()
            _write(GAPS, items)
            return item
    raise HTTPException(404, 'Capability request not found')


@router.post('/proposals/{proposal_id}/team-plan/analyze')
async def analyze_proposal_team_plan(proposal_id: str):
    """Plan the proposed team before a formal project row exists."""
    with connect() as conn:
        row = conn.execute('SELECT * FROM sys_project_proposals WHERE id=?', (proposal_id,)).fetchone()
        lifecycle = conn.execute('SELECT lifecycle_status FROM sys_project_lifecycle WHERE proposal_id=?', (proposal_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Proposal not found')
    if not lifecycle:
        raise HTTPException(409, 'Proposal lifecycle record is missing.')
    if lifecycle['lifecycle_status'] == 'rejected':
        raise HTTPException(409, 'Team planning is unavailable for a rejected Proposal.')

    proposal = dict(row)
    model = _main_model()
    try:
        installed_models = await _installed_models()
    except Exception as exc:
        raise HTTPException(502, f'Cannot verify installed Ollama models: {exc}') from exc
    if model not in installed_models:
        raise HTTPException(409, f'Main Agent model "{model}" is not installed in Ollama.')

    agents = AgentRegistry(config_path=AGENTS).list_agents()
    enabled_agents = [agent for agent in agents if agent.get('enabled')]
    capabilities = list_system_capabilities()
    tools = _tool_catalog()
    def decode(key: str, default: Any):
        try:
            return json.loads(proposal.get(key) or '')
        except (TypeError, json.JSONDecodeError):
            return default

    planner_input = {
        'proposal': {
            'proposal_id': proposal_id, 'title': proposal['title'], 'objective': proposal['objective'],
            'scope': decode('scope_json', {}), 'deliverables': decode('deliverables_json', []),
            'milestones': decode('milestones_json', []), 'timeline': decode('timeline_json', {}),
            'priority': proposal['priority'], 'risks': decode('risks_json', []),
            'assumptions': decode('assumptions_json', []),
        },
        'specialist_agents': [{
            'agent_id': a['agent_id'], 'display_name': a['display_name'],
            'capabilities': a.get('capabilities', []), 'allowed_task_types': a.get('allowed_task_types', []),
            'model': a.get('model') or None, 'enabled': a.get('enabled', False),
            'allowed_tools': a.get('allowed_tools', []), 'description': a.get('description', ''),
        } for a in enabled_agents],
        'system_capabilities': capabilities, 'registered_tools': tools,
        'installed_ollama_models': installed_models,
        'constraints': [
            'This is pre-project proposal staffing only. Do not create project tasks or assign work.',
            'Use only registered enabled Specialist Agent IDs.',
            'Validate model availability, Tool availability and Agent Tool permissions.',
            'For software/application/platform/system delivery, include a distinct QA/testing workstream unless explicitly excluded.',
            'Return a proposed team for Product Owner review; do not authorise execution.',
        ],
    }
    planner_environment = build_runtime_environment(
        agent_id="team_planner",
        model=model,
        # The planner receives a reference catalog in its input, not callable tools.
        available_tools=[],
        allowed_tools=[],
        workspace_root=WORKSPACE,
        project_root=WORKSPACE,
        read_enabled=True,
        write_enabled=False,
        ollama_base_url=OLLAMA_BASE_URL,
    )
    try:
        planned = await _call_planner(model, planner_input, planner_environment)
    except httpx.HTTPError as exc:
        detail = _describe_planner_error(exc, model)
        raise HTTPException(502, f'Main Agent team planning request failed. {detail}') from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(502, f'Main Agent team planning output could not be validated: {exc}') from exc

    agent_by_id = {a['agent_id']: a for a in enabled_agents}
    capability_by_id = {c['capability_id']: c for c in capabilities}
    tool_by_key = {str(key): tool for tool in tools for key in (tool.get('tool_id'), tool.get('function_name')) if key}
    gaps: list[dict[str, Any]] = []
    workstreams: list[dict[str, Any]] = []
    proposed_team: dict[str, dict[str, Any]] = {}
    for stream in planned.workstreams:
        stream_caps, stream_tools, candidates = [], [], []
        for cap_id in stream.required_capabilities:
            cap = capability_by_id.get(cap_id)
            if not cap or not cap.get('available'):
                gaps.append({'gap_type': 'capability', 'subject': cap_id, 'status': 'open', 'reason': 'Capability is unknown or unavailable in the system catalog.'})
            stream_caps.append({'capability_id': cap_id, 'name': cap.get('name') if cap else None, 'status': 'available' if cap and cap.get('available') else 'unavailable'})
        for tool_key in stream.required_tools:
            tool = tool_by_key.get(tool_key)
            if not tool or not tool.get('enabled'):
                gaps.append({'gap_type': 'tool', 'subject': tool_key, 'status': 'open', 'reason': 'Required Tool is missing or disabled.'})
            stream_tools.append({'tool': tool_key, 'status': 'available' if tool and tool.get('enabled') else 'unavailable'})
        for agent_id in stream.candidate_agent_ids:
            agent = agent_by_id.get(agent_id)
            if not agent:
                gaps.append({'gap_type': 'agent', 'subject': agent_id, 'status': 'open', 'reason': 'Agent is not registered and enabled.'})
                continue
            agent_model = agent.get('model') or ''
            model_ok = agent_model in installed_models
            missing = []
            for tool_key in stream.required_tools:
                tool = tool_by_key.get(tool_key)
                if tool and tool.get('enabled') and not {tool_key, tool.get('tool_id'), tool.get('function_name')}.intersection(set(agent.get('allowed_tools', []))):
                    missing.append(tool_key)
            if not model_ok:
                gaps.append({'gap_type': 'model', 'subject': agent_id, 'status': 'open', 'reason': f'Agent model is not installed or not configured: {agent_model or "not configured"}.'})
            if missing:
                gaps.append({'gap_type': 'permission', 'subject': agent_id, 'status': 'open', 'reason': f'Missing Tool permissions: {", ".join(missing)}.'})
            detail = {'agent_id': agent_id, 'agent_name': agent['display_name'], 'model': agent_model or None,
                      'model_available': model_ok, 'missing_tool_permissions': missing,
                      'status': 'ready' if model_ok and not missing else 'blocked'}
            candidates.append(detail)
            proposed_team[agent_id] = detail
        if not stream.candidate_agent_ids:
            gaps.append({'gap_type': 'agent', 'subject': stream.name, 'status': 'open', 'reason': 'No Specialist Agent was proposed for this workstream.'})
        workstreams.append({'name': stream.name, 'objective': stream.objective,
                            'required_capabilities': stream_caps, 'required_tools': stream_tools,
                            'candidate_agents': candidates, 'rationale': stream.rationale,
                            'confidence': stream.confidence})

    with connect() as conn:
        current = conn.execute('SELECT project_id,agent_allocations_json FROM sys_project_proposals WHERE id=?', (proposal_id,)).fetchone()
        previous = _latest_team_plan(conn, proposal_id=proposal_id)
        if not previous:
            allocations = json.loads(current['agent_allocations_json'] or '{}')
            previous = allocations.get('team_plan') if isinstance(allocations, dict) else None
        plan = {
            'proposal_id': proposal_id, 'project_id': current['project_id'],
            'version': int((previous or {}).get('version', 0)) + 1,
            'status': 'draft', 'analysis_method': 'Main Agent LLM with deterministic Agent, model, Capability, Tool and permission validation',
            'model_used': model, 'project_summary': planned.project_summary,
            'workstreams': workstreams, 'proposed_team': list(proposed_team.values()),
            'required_capabilities': sorted({c for stream in planned.workstreams for c in stream.required_capabilities}),
            'capability_gaps': gaps, 'risks': planned.risks, 'assumptions': planned.assumptions,
            'questions_for_owner': planned.questions_for_owner, 'created_at': now_iso(), 'updated_at': now_iso(),
        }
        plan = _persist_team_plan(conn, plan, proposal_id=proposal_id, project_id=current['project_id'])
        # Keep a compatibility mirror for older UI components; the DB table is authoritative.
        allocations = json.loads(current['agent_allocations_json'] or '{}')
        if not isinstance(allocations, dict): allocations = {'legacy_allocations': allocations}
        allocations['team_plan'] = plan
        conn.execute('UPDATE sys_project_proposals SET agent_allocations_json=?,updated_at=? WHERE id=?',
                     (json.dumps(allocations, ensure_ascii=False), now_iso(), proposal_id))
        project_id = current['project_id']
    if project_id:
        plans = _read(PLANS, {})
        plans[project_id] = plan
        _write(PLANS, plans)
    return plan


@router.get('/proposals/{proposal_id}/team-plan')
def get_proposal_team_plan(proposal_id: str):
    with connect() as conn:
        row = conn.execute('SELECT project_id,agent_allocations_json FROM sys_project_proposals WHERE id=?', (proposal_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Proposal not found')
        plan = _latest_team_plan(conn, proposal_id=proposal_id)
        if not plan:
            try:
                allocations = json.loads(row['agent_allocations_json'] or '{}')
            except json.JSONDecodeError:
                allocations = {}
            plan = allocations.get('team_plan') if isinstance(allocations, dict) else None
    if not plan:
        raise HTTPException(404, 'Proposal Team Plan has not been generated')
    return plan


@router.post('/proposals/{proposal_id}/team-plan/approve')
def approve_proposal_team_plan(proposal_id: str):
    with connect() as conn:
        row = conn.execute('SELECT project_id,agent_allocations_json FROM sys_project_proposals WHERE id=?', (proposal_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Proposal not found')
        plan = _latest_team_plan(conn, proposal_id=proposal_id)
        allocations = json.loads(row['agent_allocations_json'] or '{}')
        if not plan and isinstance(allocations, dict):
            plan = allocations.get('team_plan')
        if not plan:
            raise HTTPException(404, 'Proposal Team Plan not found')
        unresolved = [gap for gap in plan.get('capability_gaps', []) if gap.get('status') != 'resolved']
        blocked = [agent for agent in plan.get('proposed_team', []) if agent.get('status') != 'ready']
        if not plan.get('workstreams') or not plan.get('proposed_team'):
            raise HTTPException(409, 'The Team Plan must contain at least one workstream and one registered Specialist Agent.')
        if unresolved or blocked:
            raise HTTPException(409, 'Resolve all capability, Agent, model, Tool and permission gaps, then regenerate the Team Plan before approval.')
        plan['status'] = 'owner_approved'
        plan['approved_at'] = now_iso()
        plan['updated_at'] = now_iso()
        # Approval is independent of Project creation; an existing Project is linked when present.
        if row['project_id']:
            plan['project_id'] = row['project_id']
        plan = _persist_team_plan(conn, plan, proposal_id=proposal_id, project_id=row['project_id'])
        allocations = allocations if isinstance(allocations, dict) else {'legacy_allocations': allocations}
        allocations['team_plan'] = plan
        conn.execute('UPDATE sys_project_proposals SET agent_allocations_json=?,updated_at=? WHERE id=?',
                     (json.dumps(allocations, ensure_ascii=False), now_iso(), proposal_id))
        project_id = row['project_id']
    if project_id:
        plans = _read(PLANS, {})
        plans[project_id] = plan
        _write(PLANS, plans)
    return plan

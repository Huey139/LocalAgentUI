"""Deterministic first-pass routing for Main Agent requests.

The router decides which capability classes are exposed to the model. It does
not execute tools, dispatch Agents, or grant project/governance permissions.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

IntentMode = Literal["direct_response", "tool_query", "agent_delegation"]


@dataclass(frozen=True)
class IntentDecision:
    mode: IntentMode
    reason: str
    project_tools: bool = False
    proposal_tools: bool = False
    management_tools: bool = False
    database_tools: bool = False
    web_search: bool = False
    allow_agent_delegation: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_TOOL_CUES = (
    r"\b(show|list|find|search|read|open|inspect|check|query|look up|retrieve|create|update|assign)\b",
    r"(查询|查找|搜索|读取|打开|查看|列出|检查|获取|创建|更新|分配)",
)
_DELEGATION_CUES = (
    r"\b(delegate|assign to an agent|use a specialist|ask the .* agent|coordinate agents)\b",
    r"\b(comprehensive analysis|in-depth analysis|multi-step|end-to-end|architecture design|technical assessment)\b",
    r"(委派|分配给.*Agent|使用.*专家|多步骤|端到端|全面分析|深入分析|架构设计|技术评估)",
)


def _has(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def classify_intent(
    user_text: str,
    *,
    project_tools: bool = False,
    proposal_tools: bool = False,
    management_tools: bool = False,
    database_tools: bool = False,
    web_search: bool = False,
) -> IntentDecision:
    """Classify a request and determine which capability groups may be exposed.

    Explicit data/project/management/proposal operations are Tool Query work.
    Explicit specialist requests and clearly complex analytical work may be
    delegated. General explanations and discussion remain Direct Response.
    """
    text = (user_text or "").strip()
    if not text:
        return IntentDecision("direct_response", "empty request")

    needs_tools = any((project_tools, proposal_tools, management_tools, database_tools, web_search))
    if needs_tools:
        return IntentDecision(
            "tool_query",
            "request matches one or more registered tool capabilities",
            project_tools=project_tools,
            proposal_tools=proposal_tools,
            management_tools=management_tools,
            database_tools=database_tools,
            web_search=web_search,
            allow_agent_delegation=False,
        )

    if _has(_DELEGATION_CUES, text):
        return IntentDecision(
            "agent_delegation",
            "explicit specialist request or clearly multi-step specialist work",
            allow_agent_delegation=True,
        )

    # Generic verbs alone are insufficient to trigger delegation. The request
    # must signal both substantial scope and a specialist-oriented outcome.
    substantial = _has((r"\b(design|develop|evaluate|compare|audit|investigate|optimise|optimize|implement|refactor)\b",
                        r"(设计|开发|评估|比较|审计|调查|优化|实现|重构)"), text)
    specialist_outcome = _has((r"\b(model|forecast|algorithm|architecture|security|performance|data pipeline|root cause)\b",
                               r"(模型|预测|算法|架构|安全|性能|数据管道|根因)"), text)
    if substantial and specialist_outcome:
        return IntentDecision(
            "agent_delegation",
            "substantial task with a specialist-oriented technical outcome",
            allow_agent_delegation=True,
        )

    return IntentDecision("direct_response", "no registered tool operation or delegation need detected")

"""LangGraph 图定义：串联 9 个节点。

线性流程：拆解 → 抓取 → 清洗 → 分析 → 测算 → 风控 → 打分 → 报告 → 记忆。
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from dianshang.agent import nodes
from dianshang.agent.state import AgentState


def build_graph():
    """构建并编译选品调研图。"""
    g = StateGraph(AgentState)
    g.add_node("task_decompose", nodes.task_decompose)
    g.add_node("data_fetch", nodes.data_fetch)
    g.add_node("data_clean", nodes.data_clean)
    g.add_node("analyze", nodes.analyze)
    g.add_node("profit_calc", nodes.profit_calc)
    g.add_node("risk_check", nodes.risk_check)
    g.add_node("score", nodes.score)
    g.add_node("report", nodes.report)
    g.add_node("memory_save", nodes.memory_save)

    g.add_edge(START, "task_decompose")
    g.add_edge("task_decompose", "data_fetch")
    g.add_edge("data_fetch", "data_clean")
    g.add_edge("data_clean", "analyze")
    g.add_edge("analyze", "profit_calc")
    g.add_edge("profit_calc", "risk_check")
    g.add_edge("risk_check", "score")
    g.add_edge("score", "report")
    g.add_edge("report", "memory_save")
    g.add_edge("memory_save", END)
    return g.compile()


# 编译后的图单例
selection_graph = build_graph()


def run(category: str, platform: str = "pdd") -> AgentState:
    """运行完整选品调研流程，返回最终 state。"""
    initial: AgentState = {"category": category, "platform": platform}
    final = selection_graph.invoke(initial)
    return final  # type: ignore[return-value]

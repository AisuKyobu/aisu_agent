from enum import Enum


class TaskType(str, Enum):
    DETERMINISTIC = "deterministic"
    SEARCH = "search"
    REASONING = "reasoning"
    ACTION = "action"
    PLANNING = "planning"


TASK_CONSTRAINTS = {
    TaskType.DETERMINISTIC: "直接回答，禁止调用任何工具。如果缺少关键信息（如查天气没给城市），直接反问用户。",
    TaskType.SEARCH: "搜索任务。最多搜索3次，搜到后立即总结回答，不要继续搜索或尝试其他方式。",
    TaskType.REASONING: "允许使用工具辅助分析。完成任务后立即结束，不要反复验证。",
    TaskType.ACTION: "直接使用可用工具执行。写代码时用 write_file 保存文件，不要在对话中输出完整代码。",
    TaskType.PLANNING: "先使用 plan_task 制定执行计划，然后严格按计划执行每一步。每步完成后用 step_complete 标记。不要执行计划外的操作。",
}

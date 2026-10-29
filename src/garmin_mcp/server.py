"""仅封装 Garmin 官方客户端的 24 项专用数据接口。返回数据不精简、不计算、不自动补齐。"""
from __future__ import annotations
import base64
import threading
from typing import Any
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations, EmbeddedResource, BlobResourceContents
from . import official
mcp = MCPServer(name="garmin-personal", instructions="仅使用 Garmin 官方个人 API。日期和范围按官方接口要求提供，直接返回官方原始数据。没有账号密码登录或高级模式。")
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_lock=threading.Lock()
_source=None
_tag=None

def reset_client():
    global _source,_tag
    with _lock:
        _source=None
        _tag=None

def call_official(name, **kwargs):
    global _source,_tag
    key=official.get_key()
    if not key:
        raise ToolError("未配置个人 API 密钥。请设置 GARMIN_PERSONAL_API_KEY 和 GARMIN_REGION，或使用个人密钥设置页面。")
    with _lock:
        tag=(official.region(),key)
        if _source is None or _tag!=tag:
            _source=official.OfficialSource(key)
            _tag=tag
        src=_source
    try:
        return src.call(lambda c:getattr(c,name)(**kwargs))
    except official.OfficialError as e:
        raise ToolError(str(e)) from None

@mcp.tool(annotations=READ_ONLY)
def get_daily_stress(start_date: str, end_date: str) -> Any:
    '每日压力。与官方客户端 get_daily_stress 一一对应。参数和日期限制沿用官方接口。Return daily stress statistics for an inclusive calendar date range.'
    return call_official('get_daily_stress', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_steps(start_date: str, end_date: str) -> Any:
    '每日步数。与官方客户端 get_daily_steps 一一对应。参数和日期限制沿用官方接口。Return daily step statistics for an inclusive calendar date range.'
    return call_official('get_daily_steps', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_hydration(start_date: str, end_date: str) -> Any:
    '每日饮水。与官方客户端 get_daily_hydration 一一对应。参数和日期限制沿用官方接口。Return daily hydration statistics for an inclusive calendar date range.'
    return call_official('get_daily_hydration', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def get_effective_weight_goals(start_date: str, end_date: str) -> Any:
    '体重目标。与官方客户端 get_effective_weight_goals 一一对应。参数和日期限制沿用官方接口。Return effective weight goals for an inclusive calendar date range.'
    return call_official('get_effective_weight_goals', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def get_weight_measurements(start_date: str, end_date: str) -> Any:
    '体重测量。与官方客户端 get_weight_measurements 一一对应。参数和日期限制沿用官方接口。Return all weight data for an inclusive calendar date range.'
    return call_official('get_weight_measurements', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_food_logs(calendar_date: str) -> Any:
    '饮食记录。与官方客户端 get_daily_food_logs 一一对应。参数和日期限制沿用官方接口。Return nutrition food logs for a calendar date.'
    return call_official('get_daily_food_logs', calendar_date=calendar_date)

@mcp.tool(annotations=READ_ONLY)
def get_user_profile_settings() -> Any:
    "个人资料设置。与官方客户端 get_user_profile_settings 一一对应。参数和日期限制沿用官方接口。Return the current user's profile settings."
    return call_official('get_user_profile_settings')

@mcp.tool(annotations=READ_ONLY)
def get_daily_sleep(calendar_date: str) -> Any:
    '单晚睡眠。与官方客户端 get_daily_sleep 一一对应。参数和日期限制沿用官方接口。Return daily sleep data for a calendar date.'
    return call_official('get_daily_sleep', calendar_date=calendar_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_sleep_summaries(start_date: str, end_date: str) -> Any:
    '多日睡眠汇总。与官方客户端 get_daily_sleep_summaries 一一对应。参数和日期限制沿用官方接口。Return daily sleep summaries for an inclusive calendar date range.'
    return call_official('get_daily_sleep_summaries', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_body_battery(start_date: str, end_date: str, *, chunks: int | None=None) -> Any:
    '身体电量。与官方客户端 get_daily_body_battery 一一对应。参数和日期限制沿用官方接口。Return daily Body Battery data for an inclusive calendar date range.'
    return call_official('get_daily_body_battery', start_date=start_date, end_date=end_date, chunks=chunks)

@mcp.tool(annotations=READ_ONLY)
def get_daily_summaries(start_date: str, end_date: str) -> Any:
    "每日健康汇总。与官方客户端 get_daily_summaries 一一对应。参数和日期限制沿用官方接口。Return user daily summaries for an inclusive calendar date range.\n\nUse the same start and end date for a single day. The response preserves\nthe endpoint's object containing a data array, even for one day."
    return call_official('get_daily_summaries', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_hrv(calendar_date: str) -> Any:
    '单日 HRV。与官方客户端 get_daily_hrv 一一对应。参数和日期限制沿用官方接口。Return heart rate variability (HRV) summary and readings for a calendar date.'
    return call_official('get_daily_hrv', calendar_date=calendar_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_hrv_summaries(start_date: str, end_date: str) -> Any:
    '多日 HRV 汇总。与官方客户端 get_daily_hrv_summaries 一一对应。参数和日期限制沿用官方接口。Return daily heart rate variability (HRV) summaries for an inclusive date range.'
    return call_official('get_daily_hrv_summaries', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def get_heart_rate_zones() -> Any:
    "心率区间。与官方客户端 get_heart_rate_zones 一一对应。参数和日期限制沿用官方接口。Return the current user's heart rate zones."
    return call_official('get_heart_rate_zones')

@mcp.tool(annotations=READ_ONLY)
def get_fitness_age(calendar_date: str) -> Any:
    '体能年龄。与官方客户端 get_fitness_age 一一对应。参数和日期限制沿用官方接口。Return fitness age data for a calendar date.'
    return call_official('get_fitness_age', calendar_date=calendar_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_heart_rate(calendar_date: str) -> Any:
    '每日心率。与官方客户端 get_daily_heart_rate 一一对应。参数和日期限制沿用官方接口。Return daily heart rate data for a calendar date.'
    return call_official('get_daily_heart_rate', calendar_date=calendar_date)

@mcp.tool(annotations=READ_ONLY)
def get_menstrual_cycle_summary(calendar_date: str) -> Any:
    '生理周期汇总。与官方客户端 get_menstrual_cycle_summary 一一对应。参数和日期限制沿用官方接口。Return menstrual-cycle summary data for a calendar date.'
    return call_official('get_menstrual_cycle_summary', calendar_date=calendar_date)

@mcp.tool(annotations=READ_ONLY)
def get_menstrual_cycle_day_view(calendar_date: str, today_date: str) -> Any:
    '生理周期日视图。与官方客户端 get_menstrual_cycle_day_view 一一对应。参数和日期限制沿用官方接口。Return the menstrual-cycle day view for a calendar date.'
    return call_official('get_menstrual_cycle_day_view', calendar_date=calendar_date, today_date=today_date)

@mcp.tool(annotations=READ_ONLY)
def get_daily_spo2(calendar_date: str) -> Any:
    '每日血氧。与官方客户端 get_daily_spo2 一一对应。参数和日期限制沿用官方接口。Return daily SpO2 and acclimation data for a calendar date.'
    return call_official('get_daily_spo2', calendar_date=calendar_date)

@mcp.tool(annotations=READ_ONLY)
def get_wellness_activity_summaries(start_date: str, end_date: str) -> Any:
    '日常活动汇总。与官方客户端 get_wellness_activity_summaries 一一对应。参数和日期限制沿用官方接口。Return wellness activity summaries for an inclusive calendar date range.'
    return call_official('get_wellness_activity_summaries', start_date=start_date, end_date=end_date)

@mcp.tool(annotations=READ_ONLY)
def search_activities(*, start: int=0, limit: int=20, start_date: str | None=None, end_date: str | None=None, activity_type: str | None=None) -> Any:
    '搜索运动记录。与官方客户端 search_activities 一一对应。参数和日期限制沿用官方接口。Return summarized activities matching the supplied search filters.'
    return call_official('search_activities', start=start, limit=limit, start_date=start_date, end_date=end_date, activity_type=activity_type)

@mcp.tool(annotations=READ_ONLY)
def get_activity(activity_id: int | str) -> Any:
    '单次运动详情。与官方客户端 get_activity 一一对应。参数和日期限制沿用官方接口。Return the activity summary/details for an activity ID.'
    return call_official('get_activity', activity_id=activity_id)

@mcp.tool(annotations=READ_ONLY)
def get_activity_workouts(activity_id: int | str) -> Any:
    '运动关联训练。与官方客户端 get_activity_workouts 一一对应。参数和日期限制沿用官方接口。Return workouts associated with an activity ID.'
    return call_official('get_activity_workouts', activity_id=activity_id)

@mcp.tool(annotations=READ_ONLY)
def download_activity(activity_id: int | str) -> EmbeddedResource:
    '下载原始运动文件。与官方客户端 download_activity 一一对应。参数和日期限制沿用官方接口。Return the original activity file as ZIP bytes, without extracting it.'
    data=call_official('download_activity', activity_id=activity_id)
    return EmbeddedResource(type="resource",resource=BlobResourceContents(uri=f"garmin-activity:{activity_id}",mimeType="application/zip",blob=base64.b64encode(data).decode("ascii")))

def main():
    mcp.run("stdio")

if __name__=="__main__":
    main()

"""
AI智能分析模块
支持两种云端格式（OpenAI Chat Completions / Anthropic Messages）和本地Ollama三种分析方式。
对截图进行活动类型识别，支持按间隔采样分析。

架构说明：
- 底层：_call_openai_api / _call_anthropic_api / _call_local_api — 通用的API调用
- 路由：_call_api — 根据配置自动选择对应的API
- 应用层：各业务方法（analyze_screenshots_in_range, merge_descriptions, generate_daily_summary）
          构建各自对应的 prompt，调用 _call_api 并解析结果
"""
import base64
import io
import json
import re
import time
from datetime import datetime
from typing import List, Optional

from PIL import Image

from PySide6.QtCore import QObject, Signal

from openai import OpenAI
import anthropic

from config import Settings
from database import DatabaseManager
from logger import log_manager


class AIAnalyzer(QObject):
    """
    AI智能分析管理类
    支持 OpenAI、Anthropic 和本地 Ollama 三种模型，对截图进行活动类型智能识别。
    按配置的截图分析间隔采样分析，避免对所有截图进行重复分析。
    """

    analysis_complete = Signal(dict)
    analysis_error = Signal(str)
    analysis_progress = Signal(int)

    def __init__(self, config_manager: Settings, db_manager: DatabaseManager):
        """
        初始化AI分析管理器

        Args:
            config_manager: 配置管理实例
            db_manager: 数据库管理实例
        """
        super().__init__()
        self._config = config_manager
        self._db = db_manager
        self._rate_limit_timestamps: List[float] = []

    # ============================================================
    # 底层 API 调用
    # ============================================================

    def _call_api(self, prompt: str, max_tokens: int = 2048,
                  image_content: Optional[dict] = None) -> str:
        """
        根据配置自动路由到对应的云端或本地API

        Args:
            prompt: 提示词文本
            max_tokens: 最大生成token数
            image_content: 图片内容（可选），传入时自动构造多模态消息

        Returns:
            str: API响应文本
        """
        provider = self._config.get("ai_settings/ai_provider", "off")
        if provider == "openai":
            return self._call_openai_api(prompt, max_tokens, image_content)
        elif provider == "anthropic":
            return self._call_anthropic_api(prompt, max_tokens, image_content)
        elif provider == "local":
            return self._call_local_api(prompt, max_tokens, image_content)
        else:
            raise ValueError("AI 分析已关闭或未配置")

    def _call_openai_format_api(self, api_key: str, api_base: str, model_name: str,
                                 prompt: str, max_tokens: int = 2048,
                                 image_content: Optional[dict] = None,
                                 provider_name: str = "OpenAI") -> str:
        """
        通用的 OpenAI Chat Completions 格式 API 调用

        Args:
            api_key: API密钥
            api_base: API地址
            model_name: 模型名称
            prompt: 提示词文本
            max_tokens: 最大生成token数
            image_content: 图片内容（可选），用于多模态分析
            provider_name: 提供商名称，用于错误信息

        Returns:
            str: API响应文本
        """
        client = OpenAI(api_key=api_key, base_url=api_base)
        messages = self._build_openai_messages(prompt, image_content)

        self._call_with_rate_limit()
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.6,
                top_p=0.95,
                presence_penalty=0,
                extra_body={
                    "top_k": 20,
                    "repetition_penalty": 1.0,
                    "enable_thinking": False,
                },  
            )
            if response.choices:
                content = response.choices[0].message.content
                model_extra = response.choices[0].message.model_extra
                # if not (content and content.strip()) and reasoning:
                if model_extra and type(model_extra) == dict:
                    for key, value in model_extra.items():
                        log_manager.info(f"[{key}]:{value}")
                log_manager.info(f"[API响应]: {content}")
                return content.strip() if content else ""
            return ""
        except Exception as e:
            error_msg = f"{provider_name} API调用失败: {str(e)}"
            log_manager.error(error_msg)
            raise ValueError(error_msg)

    def _call_openai_api(self, prompt: str, max_tokens: int = 2048,
                         image_content: Optional[dict] = None) -> str:
        """
        底层：调用 OpenAI Chat Completions 格式的API

        Args:
            prompt: 提示词文本
            max_tokens: 最大生成token数
            image_content: 图片内容（可选），用于多模态分析

        Returns:
            str: API响应文本
        """
        api_key = self._config.get("ai_settings/openai_api_key", "")
        if not api_key and image_content:
            raise ValueError("OpenAI API密钥未配置")

        api_base = self._config.get(
            "ai_settings/openai_api_base",
            "https://api.openai.com/v1"
        )
        model_name = self._config.get("ai_settings/openai_model_name", "gpt-4o")

        return self._call_openai_format_api(
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            prompt=prompt,
            max_tokens=max_tokens,
            image_content=image_content,
            provider_name="OpenAI"
        )

    def _call_anthropic_api(self, prompt: str, max_tokens: int = 2048,
                            image_content: Optional[dict] = None) -> str:
        """
        底层：调用 Anthropic Messages 格式的API

        Args:
            prompt: 提示词文本
            max_tokens: 最大生成token数
            image_content: 图片内容（可选），用于多模态分析

        Returns:
            str: API响应文本
        """
        api_key = self._config.get("ai_settings/anthropic_api_key", "")
        if not api_key and image_content:
            raise ValueError("Anthropic API密钥未配置")

        api_base = self._config.get(
            "ai_settings/anthropic_api_base",
            "https://api.anthropic.com"
        )
        model_name = self._config.get(
            "ai_settings/anthropic_model_name",
            "claude-3-5-sonnet-20241022"
        )

        client = anthropic.Anthropic(api_key=api_key, base_url=api_base)
        messages = self._build_anthropic_messages(prompt, image_content)
        self._call_with_rate_limit()
        try:
            response = client.messages.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.6,
                top_p=0.95,
                top_k=20,
                extra_body={
                    "presence_penalty": 0,
                    "repetition_penalty": 1.0,
                    "enable_thinking": False,
                },  
            )
            if response.content:
                text_parts = []
                for block in response.content:
                    if block.type == "thinking":
                        log_manager.info(f"[thinking]: {block.thinking[:200]}")
                    elif block.type == "text" and block.text.strip():
                        text_parts.append(block.text.strip())
                return " ".join(text_parts) if text_parts else ""
            return ""
        except anthropic.NotFoundError as e:
            error_msg = f"Anthropic API错误: 模型 '{model_name}', {str(e)}"
            log_manager.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Anthropic API调用失败: {str(e)}"
            log_manager.error(error_msg)
            raise ValueError(error_msg)

    def _call_local_api(self, prompt: str, max_tokens: int = 2048,
                        image_content: Optional[dict] = None) -> str:
        """
        底层：调用本地Ollama API

        Args:
            prompt: 提示词文本
            max_tokens: 最大生成token数
            image_content: 图片内容（可选），用于多模态分析

        Returns:
            str: API响应文本
        """
        base_url = self._config.get("ai_settings/ollama_base_url", "http://localhost:11434/v1")
        model_name = self._config.get("ai_settings/ollama_model_name", "modelscope.cn/unsloth/Qwen3.5-2B-MTP-GGUF")

        return self._call_openai_format_api(
            api_key="ollama",
            api_base=base_url,
            model_name=model_name,
            prompt=prompt,
            max_tokens=max_tokens,
            image_content=image_content,
            provider_name="本地"
        )

    def _build_openai_messages(self, prompt: str,
                                image_content: Optional[dict] = None) -> list:
        """
        构建 OpenAI Chat Completions 格式的消息体

        Args:
            prompt: 提示词文本
            image_content: 图片内容（可选）

        Returns:
            list: OpenAI messages 格式的消息列表
        """
        if image_content:
            return [{"role": "user", "content": [{"type": "text", "text": prompt}, image_content]}]
        return [{"role": "user", "content": prompt}]

    def _build_anthropic_messages(self, prompt: str,
                                   image_content: Optional[dict] = None) -> list:
        """
        构建 Anthropic Messages 格式的消息体

        Args:
            prompt: 提示词文本
            image_content: 图片内容（可选）

        Returns:
            list: Anthropic messages 格式的消息列表
        """
        if image_content:
            return [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    self._convert_to_anthropic_image(image_content)
                ]
            }]
        return [{"role": "user", "content": prompt}]

    def _convert_to_anthropic_image(self, image_content: dict) -> dict:
        """
        将 OpenAI 格式的图片内容转换为 Anthropic 格式

        Args:
            image_content: OpenAI 格式的图片内容字典，含 type 和 image_url

        Returns:
            dict: Anthropic 格式的图片内容
        """
        image_url = image_content.get("image_url", {})
        url = image_url.get("url", "")
        if url.startswith("data:"):
            media_type = url.split(";")[0].replace("data:", "")
            base64_data = url.split(",")[1]
        else:
            media_type = "image/png"
            base64_data = url
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64_data,
            }
        }

    def _call_with_rate_limit(self):
        """
        频率限制控制
        根据配置的 ai_rate_limit_per_hour 控制API调用频率。
        """
        rate_limit = self._config.get("ai_settings/ai_rate_limit_per_hour", 60)
        if rate_limit <= 0:
            return

        now = time.time()
        one_hour_ago = now - 3600

        self._rate_limit_timestamps = [t for t in self._rate_limit_timestamps if t > one_hour_ago]

        if len(self._rate_limit_timestamps) >= rate_limit:
            sleep_time = 3600 - (now - self._rate_limit_timestamps[0])
            if sleep_time > 0:
                log_manager.info(f"AI分析频率限制: 等待 {sleep_time:.0f} 秒")
                time.sleep(sleep_time)

        self._rate_limit_timestamps.append(time.time())

    def _check_ai_available(self) -> bool:
        """
        检查AI提供商是否已配置

        Returns:
            bool: AI可用返回True，否则返回False
        """
        return self._config.get("ai_settings/ai_provider", "off") != "off"

    def test_api_connection(self, provider: str = None) -> dict:
        """
        测试AI API连接是否正常（轻量级，不涉及图片）

        Args:
            provider: "openai" / "anthropic" / "local"，None则使用当前配置

        Returns:
            dict: {"success": bool, "message": str, "provider": str}
        """
        if provider is None:
            provider = self._config.get("ai_settings/ai_provider", "openai")

        test_prompt = "请直接回复'OK'来确认API连接正常，不要回复其他内容。"

        try:
            if provider == "openai":
                api_key = self._config.get("ai_settings/openai_api_key", "")
                if not api_key:
                    return {"success": False, "message": "OpenAI API密钥未配置", "provider": "openai"}
                result = self._call_openai_api(test_prompt, max_tokens=81920)
            elif provider == "anthropic":
                api_key = self._config.get("ai_settings/anthropic_api_key", "")
                if not api_key:
                    return {"success": False, "message": "Anthropic API密钥未配置", "provider": "anthropic"}
                result = self._call_anthropic_api(test_prompt, max_tokens=81920)
            elif provider == "local":
                result = self._call_local_api(test_prompt, max_tokens=81920)
            else:
                return {"success": False, "message": f"未知的AI提供商: {provider}", "provider": provider}

            text = result.strip() if result else ""
            if text:
                return {"success": True, "message": f"连接成功: {text[:80]}", "provider": provider}
            else:
                return {"success": False, "message": "API返回空响应", "provider": provider}
        except Exception as e:
            return {"success": False, "message": str(e), "provider": provider}

    # ============================================================
    # 业务：截图分析
    # ============================================================

    def analyze_screenshots_in_range(self, start_time: str, end_time: str) -> dict:
        """
        分析指定时间范围内的截图
        按配置的截图分析间隔采样分析

        Args:
            start_time: 开始时间，ISO格式字符串
            end_time: 结束时间，ISO格式字符串

        Returns:
            dict: 分析结果，包含活动类型和统计信息
        """
        try:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
        except ValueError as e:
            error_msg = f"时间格式错误: {e}"
            log_manager.error(error_msg)
            self.analysis_error.emit(error_msg)
            return {}

        screenshots = self._db.get_screenshots_in_range(start_dt, end_dt)
        if not screenshots:
            error_msg = f"时间段 {start_time} 至 {end_time} 内没有截图记录"
            log_manager.warning(error_msg)
            self.analysis_error.emit(error_msg)
            return {}

        analysis_interval = self._config.get("image_settings/ai_analysis_interval", 60)
        
        # 按间隔分组，取每个时段的最后一张图
        sampled_screenshots = []
        for i in range(0, len(screenshots), analysis_interval):
            chunk = screenshots[i:i + analysis_interval]
            sampled_screenshots.append(chunk[-1])  # 取每段最后一张

        total = len(sampled_screenshots)
        log_manager.info(
            f"开始AI截图分析: 总截图 {len(screenshots)} 张，"
            f"采样 {total} 张（间隔 {analysis_interval} 张，取每段最后一张）"
        )

        all_results = []
        for i, screenshot in enumerate(sampled_screenshots):
            progress = int((i / total) * 90)
            self.analysis_progress.emit(progress)

            screenshot_id = getattr(screenshot, "id", None)
            screenshot_time = getattr(screenshot, "timestamp", None)

            if not screenshot_id or not screenshot_time:
                continue

            try:
                result = self._analyze_single(screenshot)
                if result:
                    result["screenshot_id"] = screenshot_id
                    result["timestamp"] = (
                        screenshot_time.isoformat()
                        if hasattr(screenshot_time, 'isoformat')
                        else str(screenshot_time)
                    )
                    all_results.append(result)

                    chunk_start = screenshot_time
                    chunk_end = (
                        sampled_screenshots[i + 1].timestamp
                        if i + 1 < len(sampled_screenshots)
                        else end_dt
                    )
                    self._save_ai_activity_result(
                        screenshot_id, chunk_start, chunk_end, result, screenshot
                    )

                log_manager.info(f"截图 {i + 1}/{total} AI分析完成")

            except Exception as e:
                error_msg = f"截图 {i + 1}/{total} AI分析失败: {str(e)}"
                log_manager.error(error_msg)
                self.analysis_error.emit(error_msg)

        final_result = self._merge_results(all_results, start_time, end_time, total)
        self.analysis_progress.emit(100)
        self.analysis_complete.emit(final_result)
        log_manager.info(f"AI截图分析完成: {final_result}")
        return final_result

    def _analyze_single(self, screenshot: object) -> Optional[dict]:
        """
        对单张截图进行分析（自动路由到对应API）

        Args:
            screenshot: 截图记录对象

        Returns:
            dict: 分析结果
        """
        prompt = self._build_analysis_prompt(screenshot)
        image_content = self._build_image_content(screenshot)

        if not image_content:
            return None

        result_text = self._call_api(prompt, max_tokens=81920, image_content=image_content)
        return self._parse_response(result_text, screenshot)

    def _build_analysis_prompt(self, screenshot: object) -> str:
        """
        构建单张截图的分析提示词

        Args:
            screenshot: 截图记录对象

        Returns:
            str: 分析提示词
        """
        window_title = getattr(screenshot, "window_title", "") or ""

        return f"""请分析这张桌面截图，识别用户的行为。

窗口标题：{window_title if window_title else "未知"}

请分析用户行为，然后从以下类型中选择最接近的一个活动类型名称：
- 编程开发（代码编辑器、IDE等）
- 文档写作（Word、记事本、Markdown等）
- 网页浏览（浏览器、网页应用等）
- 视频会议（Zoom、Teams、腾讯会议等）
- 娱乐休闲（视频、游戏、音乐等）
- 设计创作（PS、Figma、CAD等）
- 办公处理（Excel、PPT、邮件等）
- 社交聊天（微信、QQ、钉钉等）
- 其他

请以JSON格式返回结果，格式如下：
{{
    "activity_type": "活动类型名称",
    "description": "描述用户行为，不超过100个字符",
    "confidence": "置信度，0~1之间的浮点数"
}}"""

    def _build_image_content(self, screenshot: object) -> Optional[dict]:
        """
        将单张截图转换为base64编码的内容
        若图像长或宽超出配置的最大尺寸，则锁定长宽比缩放后再编码

        Args:
            screenshot: 截图记录对象

        Returns:
            dict: 包含 image_url 类型的内容，失败返回None
        """
        filepath = getattr(screenshot, "filepath", None) or getattr(screenshot, "file_path", None)
        if not filepath or not self._file_exists(filepath):
            return None

        try:
            max_size = self._config.get("ai_settings/ai_analysis_max_image_size", 1024)

            image = Image.open(filepath)
            original_format = image.format

            width, height = image.size
            if width > max_size or height > max_size:
                ratio = min(max_size / width, max_size / height)
                new_size = (int(width * ratio), int(height * ratio))
                image = image.resize(new_size, Image.LANCZOS)
                log_manager.info(
                    f"图像已缩放: {filepath} ({width}x{height} -> {new_size[0]}x{new_size[1]})"
                )

            buffer = io.BytesIO()
            save_format = "JPEG" if original_format == "JPEG" else "PNG"
            image.save(buffer, format=save_format)
            image_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

            mime_type = "image/jpeg"
            if filepath.lower().endswith(".png"):
                mime_type = "image/png"

            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
            }
        except Exception as e:
            log_manager.warning(f"读取截图文件失败: {filepath}, 错误: {str(e)}")
            return None

    def _parse_response(self, response_text: str, screenshot: object) -> dict:
        """
        解析AI对单张截图的响应

        Args:
            response_text: AI响应文本
            screenshot: 截图记录对象

        Returns:
            dict: 解析后的结果字典
        """
        try:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                json_str = json_match.group()
                result = json.loads(json_str)
                return {
                    "activity_type": result.get("activity_type", "未分类"),
                    "description": result.get("description", ""),
                    "confidence": result.get("confidence", 0.8),
                }
        except Exception as e:
            log_manager.warning(f"解析AI响应失败: {e}, 响应: {response_text}")

        return {
            "activity_type": "未分类",
            "description": response_text[:100] if response_text else "",
            "confidence": 0.5,
        }

    def _save_ai_activity_result(self, screenshot_id: int, chunk_start: datetime,
                                  chunk_end: datetime, result: dict, screenshot: object):
        """
        保存AI分析结果到活动记录

        Args:
            screenshot_id: 截图ID
            chunk_start: 时间段开始时间
            chunk_end: 时间段结束时间
            result: AI分析结果
            screenshot: 分析的截图记录
        """
        try:
            window_title = getattr(screenshot, "window_title", "") or ""
            activity_type = result.get("activity_type", "未分类")
            confidence = result.get("confidence", 0.8)
            description = result.get("description", "")

            self._db.add_activity(
                start_time=chunk_start,
                end_time=chunk_end,
                activity_type=activity_type,
                window_title=window_title,
                screenshot_id=screenshot_id,
                confidence=confidence,
                description=description,
            )
            log_manager.info(
                f"AI 分析活动记录已保存：截图{screenshot_id} -> {activity_type}"
            )
        except Exception as e:
            log_manager.error(f"保存AI分析结果失败: {e}")

    def _merge_results(self, results: list, start_time: str,
                       end_time: str, total_screenshots: int) -> dict:
        """
        合并多个截图的分析结果

        Args:
            results: 各截图分析结果列表
            start_time: 分析开始时间
            end_time: 分析结束时间
            total_screenshots: 截图总数

        Returns:
            dict: 合并后的分析结果
        """
        if not results:
            return {
                "activity_type": "未分类",
                "start_time": start_time,
                "end_time": end_time,
                "total_screenshots": total_screenshots,
                "analyzed_screenshots": 0,
                "activities": [],
            }

        activity_counts = {}
        for r in results:
            act_type = r.get("activity_type", "未分类")
            activity_counts[act_type] = activity_counts.get(act_type, 0) + 1

        main_activity = (
            max(activity_counts.items(), key=lambda x: x[1])[0]
            if activity_counts else "未分类"
        )

        return {
            "activity_type": main_activity,
            "start_time": start_time,
            "end_time": end_time,
            "total_screenshots": total_screenshots,
            "analyzed_screenshots": len(results),
            "activities": activity_counts,
            "screenshot_details": results,
        }

    # ============================================================
    # 业务：合并连续活动描述
    # ============================================================

    def merge_descriptions(self, descriptions: list, activity_type: str) -> str:
        """
        使用AI合并同一活动类型的多条描述为一条简洁的概述

        Args:
            descriptions: 同一活动类型多条描述文本列表
            activity_type: 活动类型名称

        Returns:
            str: 合并后的描述文本
        """
        if not self._check_ai_available() or not descriptions:
            return descriptions[0] if descriptions else ""

        valid_descriptions = [d for d in descriptions if d and d.strip()]
        if not valid_descriptions:
            return ""

        prompt = self._build_merge_prompt(valid_descriptions, activity_type)

        try:
            return self._call_api(prompt, max_tokens=81920)
        except Exception as e:
            log_manager.warning(f"AI合并描述失败: {e}")
            return valid_descriptions[0]

    def _build_merge_prompt(self, descriptions: list, activity_type: str) -> str:
        """
        构建合并描述的提示词

        Args:
            descriptions: 有效描述文本列表
            activity_type: 活动类型名称

        Returns:
            str: 合并描述用的提示词
        """
        lines = "\n".join(
            f"{i + 1}. {d}" for i, d in enumerate(descriptions)
        )
        return (
            f"你正在分析一组用户活动记录，这些记录都属于同一活动类型「{activity_type}」。\n\n"
            "以下是该时间段内多条连续活动记录的描述"
            "（方括号内为当时使用的窗口标题，其后为活动描述）：\n\n"
            f"{lines}\n\n"
            "请将这些描述合并为一段简洁、连贯的概述（约50-100字），"
            "概括用户在此期间的主要行为。\n"
            "要求：\n"
            "1. 直接给出合并后的概述文本，不要添加任何前缀或格式标记\n"
            "2. 保留关键信息、窗口上下文和行为细节\n"
            "3. 语言通顺自然"
        )

    # ============================================================
    # 业务：生成每日总结
    # ============================================================

    def generate_daily_summary(self, activities_data: list, date_str: str) -> str:
        """
        使用AI生成每日工作活动总结

        Args:
            activities_data: 活动数据列表，每项含 activity_type, start_time, end_time,
                             description, window_title
            date_str: 日期字符串

        Returns:
            str: 以HTML格式返回的每日总结
        """
        if not activities_data:
            return "<p style='color:#888;'>暂无活动记录</p>"

        if not self._check_ai_available():
            return "<p style='color:#888;'>AI分析已关闭，请先在设置中配置AI提供商</p>"

        prompt = self._build_summary_prompt(activities_data, date_str)
        try:
            log_manager.info(f"AI生成每日总结提示词:\n {prompt}")
            return self._call_api(prompt, max_tokens=81920)
        except Exception as e:
            log_manager.warning(f"AI生成每日总结失败: {e}")
            return f"<p style='color:#e74c3c;'>生成总结失败: {e}</p>"

    def _build_summary_prompt(self, activities_data: list, date_str: str) -> str:
        """
        构建每日总结的提示词

        Args:
            activities_data: 活动数据列表
            date_str: 日期字符串

        Returns:
            str: 每日总结用的提示词
        """
        activities_text = ""
        for i, act in enumerate(activities_data, 1):
            act_type = act.get("activity_type", "未分类")
            start = act.get("start_time", "")
            end = act.get("end_time", "")
            start_str = start.strftime("%H:%M") if hasattr(start, 'strftime') else str(start)
            end_str = end.strftime("%H:%M") if hasattr(end, 'strftime') else str(end)
            desc = act.get("description", "")
            window_title = act.get("window_title", "")
            activities_text += f"{i}. [{start_str}-{end_str}] {act_type}"
            if window_title:
                activities_text += f" ({window_title})"
            if desc:
                activities_text += f" - {desc}"
            activities_text += "\n"
            html_template = """
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <title>ScreenLogger 每日总结 - {date_str}</title>
            </head>
            <body>
                <header>
                    <h1>ScreenLogger 每日总结</h1>
                    <p>报告日期：{date_str}</p>
                </header>

                <main>
                    <section>
                        <h2>📊 主要活动分布</h2>
                        <p>{lines}</p>
                    </section>

                    <section>
                        <h2>🚀 整体效率分析</h2>
                        <p>{efficiency}</p>
                    </section>
                </main>

                <footer>
                    <p>由 ScreenLogger 自动生成</p>
                </footer>
            </body>
            </html>
            """


        prompt = (
            f"# 角色设定\n"
            f"你是一位资深的个人效率诊断专家与企业运营分析师，擅长从碎片化的活动记录中提炼核心成果、识别时间损耗，并提供极具实操性的效率提升策略。\n\n"
            
            f"# 任务背景\n"
            f"用户在 {date_str} 记录了以下完整的活动轨迹，请基于这些数据为其生成一份结构化、深洞察的每日工作总结与效率分析报告。\n\n"
            
            f"# 工作记录\n"
            f"{activities_text}\n\n"
            
            f"# 任务指令\n"
            f"请严格按照以下四个模块构建你的分析逻辑：\n"
            f"1. **工作总览**：精炼概括当日核心产出与主轴，不罗列流水账。\n"
            f"2. **活动分布**：将活动按属性归类（如：深度工作、会议沟通、行政琐事），分析时间投入占比。\n"
            f"3. **关键行为描述**：识别最高价值的产出动作与潜在的时间黑洞（如无意义的频繁切换）。\n"
            f"4. **整体效率分析**：给出效率评分（1-10），并明确指出1条保持项与1条改进项，拒绝空泛鸡汤。\n\n"
            
            f"# 输出约束\n"
            f"- 语言风格：专业客观、数据导向，使用中文输出，杜绝废话与套话。\n"
            f"- 篇幅限制：核心文本分析需精简干练，总字数控制在400字以内（为HTML标签留出空间）。\n"
            f"- 安全准则：不确定的数据请明确标注“需核实”，严禁自行编造活动细节。\n\n"
            
            f"# 输出格式\n"
            f"必须严格遵循以下HTML模板结构输出，语义化标签需准确对应内容层级：\n"
            f"{html_template}\n\n"
            
            f"# 执行要求\n"
            f"请跳过任何思考过程与前置解释说明，直接输出纯净的HTML代码片段：\n"
        )
        return prompt

    # ============================================================
    # 辅助方法
    # ============================================================

    def _file_exists(self, filepath: str) -> bool:
        """检查文件是否存在"""
        import os
        return os.path.exists(filepath)
    
    

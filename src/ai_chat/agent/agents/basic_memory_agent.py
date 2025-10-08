from typing import (
    AsyncIterator,
    List,
    Dict,
    Any,
    Callable,
    Literal,
    Union,
    Optional,
)
import json
from loguru import logger
from .agent_interface import AgentInterface
from ..output_types import SentenceOutput, DisplayText
from ..stateless_llm.stateless_llm_interface import StatelessLLMInterface
from ..stateless_llm.openai_compatible_llm import AsyncLLM as OpenAICompatibleAsyncLLM
from ...chat_history_manager import get_history
from ..transformers import (
    sentence_divider,
    actions_extractor,
    tts_filter,
    display_processor,
)
from ...config_manager import TTSPreprocessorConfig
from ..input_types import BatchInput, TextSource
from prompts import prompt_loader
from ...mcpp.tool_manager import ToolManager
from ...mcpp.json_detector import StreamJSONDetector
from ...conversations.laundry_handler import LaundryHandler
from ...mcpp.types import ToolCallObject
from ...mcpp.tool_executor import ToolExecutor


class BasicMemoryAgent(AgentInterface):
    """Agent with basic chat memory and tool calling support."""

    _system: str = "You are a helpful assistant."
    # Limit the in-memory conversation length to avoid prompt bloat and latency growth
    MAX_MEMORY_MESSAGES: int = 6

    def __init__(
        self,
        llm: StatelessLLMInterface,
        system: str,
        live2d_model,
        tts_preprocessor_config: TTSPreprocessorConfig = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        use_mcpp: bool = False,
        interrupt_method: Literal["system", "user"] = "user",
        tool_prompts: Dict[str, str] = None,
        tool_manager: Optional[ToolManager] = None,
        tool_executor: Optional[ToolExecutor] = None,
        mcp_prompt_string: str = "",
    ):
        """Initialize agent with LLM and configuration."""
        super().__init__()
        self._memory = []
        self._live2d_model = live2d_model
        self._tts_preprocessor_config = tts_preprocessor_config
        self._faster_first_response = faster_first_response
        self._segment_method = segment_method
        self._use_mcpp = use_mcpp
        self.interrupt_method = interrupt_method
        self._tool_prompts = tool_prompts or {}
        self._interrupt_handled = False
        self.prompt_mode_flag = False

        self._tool_manager = tool_manager
        self._tool_executor = tool_executor
        self._mcp_prompt_string = mcp_prompt_string
        self._json_detector = StreamJSONDetector()
        self._laundry_handler = LaundryHandler()
        self._websocket_send_func = None  # Will be set by external caller

        self._formatted_tools_openai = []
        self._formatted_tools_claude = []
        if self._tool_manager:
            self._formatted_tools_openai = self._tool_manager.get_formatted_tools(
                "OpenAI"
            )
            self._formatted_tools_claude = self._tool_manager.get_formatted_tools(
                "Claude"
            )
            logger.debug(
                f"Agent received pre-formatted tools - OpenAI: {len(self._formatted_tools_openai)}, Claude: {len(self._formatted_tools_claude)}"
            )
        else:
            logger.debug(
                "ToolManager not provided, agent will not have pre-formatted tools."
            )

        self._set_llm(llm)
        self.set_system(system if system else self._system)

        if self._use_mcpp and not all(
            [
                self._tool_manager,
                self._tool_executor,
                self._json_detector,
            ]
        ):
            logger.warning(
                "use_mcpp is True, but some MCP components are missing in the agent. Tool calling might not work as expected."
            )
        elif not self._use_mcpp and any(
            [
                self._tool_manager,
                self._tool_executor,
                self._json_detector,
            ]
        ):
            logger.warning(
                "use_mcpp is False, but some MCP components were passed to the agent."
            )

        logger.info("BasicMemoryAgent initialized.")

    def set_websocket_send_func(self, websocket_send_func):
        """Set the WebSocket send function for laundry responses."""
        self._websocket_send_func = websocket_send_func

    def _set_llm(self, llm: StatelessLLMInterface):
        """Set the LLM for chat completion."""
        self._llm = llm
        self.chat = self._chat_function_factory()

    def set_system(self, system: str):
        """Set the system prompt."""
        logger.debug(f"Memory Agent: Setting system prompt: '''{system}'''")

        if self.interrupt_method == "user":
            system = f"{system}\n\nIf you received `[interrupted by user]` signal, you were interrupted."

        self._system = system

    def _add_message(
        self,
        message: Union[str, List[Dict[str, Any]]],
        role: str,
        display_text: DisplayText | None = None,
        skip_memory: bool = False,
    ):
        """Add message to memory."""
        if skip_memory:
            return

        text_content = ""
        if isinstance(message, list):
            for item in message:
                if item.get("type") == "text":
                    text_content += item["text"] + " "
            text_content = text_content.strip()
        elif isinstance(message, str):
            text_content = message
        else:
            logger.warning(
                f"_add_message received unexpected message type: {type(message)}"
            )
            text_content = str(message)

        if not text_content and role == "assistant":
            return

        message_data = {
            "role": role,
            "content": text_content,
        }

        if display_text:
            if display_text.name:
                message_data["name"] = display_text.name
            if display_text.avatar:
                message_data["avatar"] = display_text.avatar

        if (
            self._memory
            and self._memory[-1]["role"] == role
            and self._memory[-1]["content"] == text_content
        ):
            return

        self._memory.append(message_data)
        # Cap the memory window to avoid growing latency and token usage over time
        if len(self._memory) > self.MAX_MEMORY_MESSAGES:
            self._memory = self._memory[-self.MAX_MEMORY_MESSAGES:]

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """Load memory from chat history."""
        messages = get_history(conf_uid, history_uid)

        self._memory = []
        for msg in messages:
            role = "user" if msg["role"] == "human" else "assistant"
            content = msg["content"]
            if isinstance(content, str) and content:
                self._memory.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )
            else:
                logger.warning(f"Skipping invalid message from history: {msg}")
        logger.info(f"Loaded {len(self._memory)} messages from history.")

    def handle_interrupt(self, heard_response: str) -> None:
        """Handle user interruption."""
        if self._interrupt_handled:
            return

        self._interrupt_handled = True

        if self._memory and self._memory[-1]["role"] == "assistant":
            if not self._memory[-1]["content"].endswith("..."):
                self._memory[-1]["content"] = heard_response + "..."
            else:
                self._memory[-1]["content"] = heard_response + "..."
        else:
            if heard_response:
                self._memory.append(
                    {
                        "role": "assistant",
                        "content": heard_response + "...",
                    }
                )

        interrupt_role = "system" if self.interrupt_method == "system" else "user"
        self._memory.append(
            {
                "role": interrupt_role,
                "content": "[Interrupted by user]",
            }
        )
        logger.info(f"Handled interrupt with role '{interrupt_role}'.")

    def _to_text_prompt(self, input_data: BatchInput) -> str:
        """Format input data to text prompt."""
        message_parts = []

        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                message_parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                message_parts.append(
                    f"[User shared content from clipboard: {text_data.content}]"
                )

        if input_data.images:
            message_parts.append("\n[User has also provided images]")

        return "\n".join(message_parts).strip()

    def _to_messages(self, input_data: BatchInput) -> List[Dict[str, Any]]:
        """Prepare messages for LLM API call."""
        messages = self._memory.copy()
        user_content = []
        text_prompt = self._to_text_prompt(input_data)
        if text_prompt:
            user_content.append({"type": "text", "text": text_prompt})

        if input_data.images:
            image_added = False
            for img_data in input_data.images:
                if isinstance(img_data.data, str) and img_data.data.startswith(
                    "data:image"
                ):
                    user_content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": img_data.data, "detail": "auto"},
                        }
                    )
                    image_added = True
                else:
                    logger.error(
                        f"Invalid image data format: {type(img_data.data)}. Skipping image."
                    )

            if not image_added and not text_prompt:
                logger.warning(
                    "User input contains images but none could be processed."
                )

        if user_content:
            user_message = {"role": "user", "content": user_content}
            messages.append(user_message)

            skip_memory = False
            if input_data.metadata and input_data.metadata.get("skip_memory", False):
                skip_memory = True

            if not skip_memory:
                self._add_message(
                    text_prompt if text_prompt else "[User provided image(s)]", "user"
                )
        else:
            logger.warning("No content generated for user message.")

        return messages


    async def _openai_tool_interaction_loop(
        self,
        initial_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> AsyncIterator[Union[str, Dict[str, Any]]]:
        """Handle OpenAI interaction with tool support."""
        messages = initial_messages.copy()
        current_turn_text = ""
        pending_tool_calls: Union[List[ToolCallObject], List[Dict[str, Any]]] = []
        current_system_prompt = self._system

        while True:
            if self.prompt_mode_flag:
                if self._mcp_prompt_string:
                    current_system_prompt = (
                        f"{self._system}\n\n{self._mcp_prompt_string}"
                    )
                else:
                    logger.warning("Prompt mode active but mcp_prompt_string is empty!")
                    current_system_prompt = self._system
                tools_for_api = None
            else:
                current_system_prompt = self._system
                tools_for_api = tools

            stream = self._llm.chat_completion(
                messages, current_system_prompt, tools=tools_for_api
            )
            pending_tool_calls.clear()
            current_turn_text = ""
            assistant_message_for_api = None
            detected_prompt_json = None
            goto_next_while_iteration = False

            async for event in stream:
                if self.prompt_mode_flag:
                    if isinstance(event, str):
                        current_turn_text += event
                        if self._json_detector:
                            potential_json = self._json_detector.process_chunk(event)
                            if potential_json:
                                try:
                                    if isinstance(potential_json, list):
                                        detected_prompt_json = potential_json
                                    elif isinstance(potential_json, dict):
                                        detected_prompt_json = [potential_json]

                                    if detected_prompt_json:
                                        break
                                except Exception as e:
                                    logger.error(f"Error parsing detected JSON: {e}")
                                    if self._json_detector:
                                        self._json_detector.reset()
                                    yield f"[Error parsing tool JSON: {e}]"
                                    goto_next_while_iteration = True
                                    break
                        yield event
                else:
                    if isinstance(event, str):
                        current_turn_text += event
                        yield event
                    elif isinstance(event, list) and all(
                        isinstance(tc, ToolCallObject) for tc in event
                    ):
                        pending_tool_calls = event
                        assistant_message_for_api = {
                            "role": "assistant",
                            "content": current_turn_text if current_turn_text else None,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": tc.type,
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in pending_tool_calls
                            ],
                        }
                        break
                    elif event == "__API_NOT_SUPPORT_TOOLS__":
                        logger.warning(
                            f"LLM {getattr(self._llm, 'model', '')} has no native tool support. Switching to prompt mode."
                        )
                        self.prompt_mode_flag = True
                        if self._tool_manager:
                            self._tool_manager.disable()
                        if self._json_detector:
                            self._json_detector.reset()
                        goto_next_while_iteration = True
                        break
            if goto_next_while_iteration:
                continue

            if detected_prompt_json:
                logger.info("Processing tools detected via prompt mode JSON.")
                self._add_message(current_turn_text, "assistant")

                parsed_tools = self._tool_executor.process_tool_from_prompt_json(
                    detected_prompt_json
                )
                if parsed_tools:
                    tool_results_for_llm = []
                    if not self._tool_executor:
                        logger.error(
                            "Prompt Tool interaction requested but ToolExecutor/MCPClient is not available."
                        )
                        yield "[Error: ToolExecutor/MCPClient not configured for prompt mode]"
                        continue

                    tool_executor_iterator = self._tool_executor.execute_tools(
                        tool_calls=parsed_tools,
                        caller_mode="Prompt",
                    )
                    try:
                        while True:
                            update = await anext(tool_executor_iterator)
                            if update.get("type") == "final_tool_results":
                                tool_results_for_llm = update.get("results", [])
                                break
                            else:
                                yield update
                    except StopAsyncIteration:
                        logger.warning(
                            "Prompt mode tool executor finished without final results marker."
                        )

                    if tool_results_for_llm:
                        result_strings = [
                            res.get("content", "Error: Malformed result")
                            for res in tool_results_for_llm
                        ]
                        combined_results_str = "\n".join(result_strings)
                        messages.append(
                            {"role": "user", "content": combined_results_str}
                        )
                continue

            elif pending_tool_calls and assistant_message_for_api:
                messages.append(assistant_message_for_api)
                if current_turn_text:
                    self._add_message(current_turn_text, "assistant")

                tool_results_for_llm = []
                if not self._tool_executor:
                    logger.error(
                        "OpenAI Tool interaction requested but ToolExecutor/MCPClient is not available."
                    )
                    yield "[Error: ToolExecutor/MCPClient not configured for OpenAI mode]"
                    continue

                tool_executor_iterator = self._tool_executor.execute_tools(
                    tool_calls=pending_tool_calls,
                    caller_mode="OpenAI",
                )
                try:
                    while True:
                        update = await anext(tool_executor_iterator)
                        if update.get("type") == "final_tool_results":
                            tool_results_for_llm = update.get("results", [])
                            # 检查工具结果中是否有洗衣店视频响应
                            await self._process_laundry_tool_results(tool_results_for_llm)
                            break
                        else:
                            yield update
                except StopAsyncIteration:
                    logger.warning(
                        "OpenAI tool executor finished without final results marker."
                    )

                if tool_results_for_llm:
                    messages.extend(tool_results_for_llm)
                continue

            else:
                if current_turn_text:
                    self._add_message(current_turn_text, "assistant")
                return

    def _chat_function_factory(
        self,
    ) -> Callable[[BatchInput], AsyncIterator[Union[SentenceOutput, Dict[str, Any]]]]:
        """Create the chat pipeline function."""

        @tts_filter(self._tts_preprocessor_config)
        @display_processor()
        @actions_extractor(self._live2d_model)
        @sentence_divider(
            faster_first_response=self._faster_first_response,
            segment_method=self._segment_method,
            valid_tags=["think"],
        )
        async def chat_with_memory(
            input_data: BatchInput,
        ) -> AsyncIterator[Union[str, Dict[str, Any]]]:
            """Process chat with memory and tools."""
            self.reset_interrupt()
            self.prompt_mode_flag = False

            # 检查是否为洗衣机相关查询
            user_text = ""
            if input_data.texts:
                for text_data in input_data.texts:
                    if text_data.source == TextSource.INPUT:
                        user_text += text_data.content
            
            # 如果是洗衣机相关查询，直接调用洗衣机工具
            if user_text and self._laundry_handler.is_laundry_related_query(user_text):
                logger.info(f"🧺 检测到洗衣机相关查询: {user_text}")
                machine_id = self._laundry_handler.extract_machine_number(user_text)
                language_mode = self._laundry_handler.detect_language_mode(user_text)
                # 即刻反馈，降低主观等待
                try:
                    if language_mode == "ja":
                        yield "少々お待ちください。チュートリアルを確認します。"
                    elif language_mode == "en":
                        yield "One moment, fetching the tutorial for you."
                    else:
                        yield "稍等，我马上为您查找教程。"
                except Exception:
                    pass
                
                # 调用洗衣机MCP工具
                if self._tool_executor:
                    tool_call = self._laundry_handler.format_mcp_tool_call(
                        user_text, machine_id, language_mode
                    )
                    
                    try:
                        # 构造工具调用对象
                        from ...mcpp.types import ToolCallObject, ToolCallFunctionObject
                        tool_call_obj = ToolCallObject(
                            id=f"laundry_{hash(user_text)}",
                            type="function",
                            index=0,
                            function=ToolCallFunctionObject(
                                name=tool_call["tool_name"],
                                arguments=json.dumps(tool_call["arguments"])
                            )
                        )
                        
                        # 执行工具调用
                        final_results = []
                        async for result in self._tool_executor.execute_tools([tool_call_obj], "OpenAI"):
                            # 只处理最终的工具结果
                            if isinstance(result, dict) and result.get("type") == "final_tool_results":
                                final_results = result.get("results", [])
                                break
                        
                        # 处理工具结果
                        if final_results:
                            logger.debug(f"洗衣机工具调用返回最终结果数量: {len(final_results)}")
                            # 先处理潜在的视频播放，通过 WebSocket 通知前端
                            await self._process_laundry_tool_results(final_results)

                            # 汇总可直接对用户朗读的文本内容
                            speak_texts: list[str] = []
                            try:
                                for result in final_results:
                                    if isinstance(result, dict) and result.get("role") == "tool":
                                        content = result.get("content", "")
                                        if isinstance(content, str) and content:
                                            try:
                                                parsed = json.loads(content)
                                            except json.JSONDecodeError:
                                                parsed = None

                                            if isinstance(parsed, dict):
                                                resp_type = parsed.get("type")
                                                if resp_type == "video_response":
                                                    # 使用工具自带的 response_text 作为口头反馈
                                                    if parsed.get("response_text"):
                                                        speak_texts.append(parsed["response_text"])
                                                elif resp_type in ("text_response", "refresh_response"):
                                                    if parsed.get("content"):
                                                        speak_texts.append(parsed["content"])
                                                    elif parsed.get("message"):
                                                        speak_texts.append(parsed["message"])
                                            else:
                                                # 非 JSON 文本，直接朗读
                                                speak_texts.append(str(content))
                            except Exception as parse_err:
                                logger.error(f"解析洗衣机工具结果用于回复时出错: {parse_err}")

                            # 若收集到文本，直接回复用户这些文本
                            if speak_texts:
                                yield "\n".join(speak_texts)
                                return

                            # 否则退回到语言模式下的简短确认
                            if language_mode == "ja":
                                yield "承知いたしました。"
                            else:
                                yield "好的。"
                            return
                        else:
                            logger.warning("洗衣机工具调用没有返回最终结果")
                    except Exception as e:
                        logger.error(f"洗衣机工具调用失败: {e}")
                        # 如果工具调用失败，回退到正常流程

            messages = self._to_messages(input_data)
            tools = None
            tool_mode = None
            llm_supports_native_tools = False

            if self._use_mcpp and self._tool_manager:
                tools = None
                if isinstance(self._llm, OpenAICompatibleAsyncLLM):
                    tool_mode = "OpenAI"
                    tools = self._formatted_tools_openai
                    llm_supports_native_tools = True
                else:
                    logger.warning(
                        f"LLM type {type(self._llm)} not explicitly handled for tool mode determination."
                    )

                if llm_supports_native_tools and not tools:
                    logger.warning(
                        f"No tools available/formatted for '{tool_mode}' mode, despite MCP being enabled."
                    )

            if self._use_mcpp and tool_mode == "Claude":
                logger.debug(
                    f"Starting Claude tool interaction loop with {len(tools)} tools."
                )
                async for output in self._claude_tool_interaction_loop(
                    messages, tools if tools else []
                ):
                    yield output
                return
            elif self._use_mcpp and tool_mode == "OpenAI":
                logger.debug(
                    f"Starting OpenAI tool interaction loop with {len(tools)} tools."
                )
                async for output in self._openai_tool_interaction_loop(
                    messages, tools if tools else []
                ):
                    yield output
                return
            else:
                logger.info("Starting simple chat completion.")
                token_stream = self._llm.chat_completion(messages, self._system)
                complete_response = ""
                async for event in token_stream:
                    text_chunk = ""
                    if isinstance(event, dict) and event.get("type") == "text_delta":
                        text_chunk = event.get("text", "")
                    elif isinstance(event, str):
                        text_chunk = event
                    else:
                        continue
                    if text_chunk:
                        yield text_chunk
                        complete_response += text_chunk
                if complete_response:
                    self._add_message(complete_response, "assistant")

        return chat_with_memory

    async def chat(
        self,
        input_data: BatchInput,
    ) -> AsyncIterator[Union[SentenceOutput, Dict[str, Any]]]:
        """Run chat pipeline."""
        chat_func_decorated = self._chat_function_factory()
        async for output in chat_func_decorated(input_data):
            yield output

    def reset_interrupt(self) -> None:
        """Reset interrupt flag."""
        self._interrupt_handled = False


    async def _process_laundry_tool_results(self, tool_results):
        """Process tool results to check for laundry video responses."""
        import json
        import asyncio
        
        logger.debug(f"开始处理洗衣机工具结果，结果数量: {len(tool_results)}")
        
        if not self._websocket_send_func:
            logger.warning("No WebSocket send function available for laundry processing")
            return
            
        for i, result in enumerate(tool_results):
            try:
                logger.debug(f"处理结果 {i}: type={type(result)}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}")
                # Check if this is a tool result message
                if isinstance(result, dict) and result.get("role") == "tool":
                    content = result.get("content", "")
                    logger.debug(f"找到工具结果，内容长度: {len(content) if isinstance(content, str) else 'N/A'}")
                    if isinstance(content, str):
                        try:
                            # Try to parse as JSON
                            json_data = json.loads(content)
                            logger.debug(f"JSON解析成功，类型: {json_data.get('type')}")
                            if json_data.get("type") == "video_response":
                                logger.info(f"Detected laundry video response: {json_data}")
                            # Process through LaundryHandler
                            websocket_message = self._laundry_handler.process_mcp_tool_result(content)
                            # ✅ Send WebSocket message (直接等待，WebSocket 发送很快)
                            try:
                                await self._websocket_send_func(json.dumps(websocket_message))
                                logger.info("Sent laundry video WebSocket message to frontend")
                            except Exception as e:
                                logger.error(f"Failed to send laundry video message: {e}")
                        except json.JSONDecodeError as e:
                            logger.debug(f"JSON解析失败: {e}")
                            pass
                else:
                    logger.debug(f"结果不是工具消息，role={result.get('role') if isinstance(result, dict) else 'N/A'}")
            except Exception as e:
                logger.error(f"Error processing laundry tool result: {e}")

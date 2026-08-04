"""
写作技能 - Writer Skill

负责：
- 续写生成
- 同人创作
- 角色台词生成
- 场景描写
- 大纲扩写
"""

import re
import random
from typing import List, Dict, Any
from ..registry import BaseSkill, ToolDefinition
from ._provider import complete_text


class WriterSkill(BaseSkill):
    name = 'writer'

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name='generate_continuation',
                description='基于现有风格续写内容',
                parameters={
                    'prompt': {'type': 'string', 'desc': '续写提示'},
                    'chapter_num': {'type': 'int', 'desc': '续写章节号'},
                    'length': {'type': 'int', 'default': 500, 'desc': '目标字数'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='generate_dialogue',
                description='生成角色对话',
                parameters={
                    'char1': {'type': 'string', 'required': True, 'desc': '角色1'},
                    'char2': {'type': 'string', 'required': True, 'desc': '角色2'},
                    'topic': {'type': 'string', 'desc': '对话主题'},
                    'turns': {'type': 'int', 'default': 3, 'desc': '对话轮数'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='describe_scene',
                description='生成场景描写',
                parameters={
                    'location': {'type': 'string', 'desc': '地点'},
                    'time': {'type': 'string', 'default': '夜晚', 'desc': '时间'},
                    'mood': {'type': 'string', 'default': '神秘', 'desc': '氛围'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='expand_outline',
                description='扩写故事大纲',
                parameters={
                    'outline': {'type': 'string', 'required': True, 'desc': '大纲内容'},
                    'detail_level': {'type': 'string', 'default': 'medium', 'desc': '详细程度: low/medium/high'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='character_poem',
                description='生成人物判词/诗句',
                parameters={
                    'char_name': {'type': 'string', 'required': True, 'desc': '人物名称'},
                    'style': {'type': 'string', 'default': '七言', 'desc': '风格: 五言/七言/词'},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name == 'generate_continuation':
            return self._continuation(
                params.get('prompt', ''),
                params.get('chapter_num', 0),
                params.get('length', 500),
            )
        elif tool_name == 'generate_dialogue':
            return self._dialogue(
                params.get('char1', ''),
                params.get('char2', ''),
                params.get('topic', ''),
                params.get('turns', 3),
            )
        elif tool_name == 'describe_scene':
            return self._scene(
                params.get('location', ''),
                params.get('time', '夜晚'),
                params.get('mood', '神秘'),
            )
        elif tool_name == 'expand_outline':
            return self._expand(
                params.get('outline', ''),
                params.get('detail_level', 'medium'),
            )
        elif tool_name == 'character_poem':
            return self._poem(
                params.get('char_name', ''),
                params.get('style', '七言'),
            )
        return {'error': f'Unknown tool: {tool_name}', 'tool': tool_name}

    def _continuation(self, prompt: str, chapter_num: int, length: int) -> Dict:
        provider_result = self._provider_result(
            "generate_continuation",
            f"请根据以下提示续写第{chapter_num}章，目标约{length}字。\n提示：{prompt or '继续当前情节'}",
            "content",
            {"prompt": prompt, "chapter": chapter_num, "target_length": length},
        )
        if provider_result is not None:
            return provider_result

        sample_style = ''
        if self.store and self.store.chapters:
            idx = min(chapter_num - 1, len(self.store.chapters) - 1) if chapter_num > 0 else 0
            ch = self.store.get_chapter(idx)
            if ch:
                sample_style = ch.content[:500]

        continuation = f"""（注：写作技能当前为模板生成模式，接入 LLM 后可生成高质量内容）

{prompt or '...'}

夜色如墨，山风呼啸。
林木间鬼影幢幢，远处传来隐隐的哭号声，令人毛骨悚然。
主角握紧了手中的法器，眼神凝重地望着前方那片幽暗的密林。

"你确定要进去？"身旁的同伴低声问道，声音中带着一丝颤抖。

"必须进去。"主角的声音平静而坚定，"有些东西，总得有人去面对。"

说罢，他迈步向前，身影很快便消失在了浓重的雾气之中。

林深处，一双幽绿的眼睛缓缓睁开...

---
（以上为示例续写，实际使用时将调用 LLM 根据原文风格生成）
"""

        return {
            'tool': 'generate_continuation',
            'prompt': prompt,
            'chapter': chapter_num,
            'target_length': length,
            'content': continuation[:length * 2],
            'style_reference': sample_style[:200] if sample_style else '',
            'available': False,
            'status': 'unavailable',
            'error_code': 'provider_unavailable',
            'note': '未配置可用 Provider；返回的内容仅为兼容性示例，不代表真实续写结果',
        }

    def _dialogue(self, char1: str, char2: str, topic: str, turns: int) -> Dict:
        topic = topic or '最近的经历'
        provider_result = self._provider_result(
            "generate_dialogue",
            f"请为{char1}和{char2}围绕“{topic}”生成{turns}轮对话，只返回对话正文。",
            "dialogue",
            {"char1": char1, "char2": char2, "topic": topic, "turns": turns},
        )
        if provider_result is not None:
            return provider_result

        dialogues = [
            {f'{char1}': f'{char2}，你觉得{topic}这事，靠谱吗？'},
            {f'{char2}': f'不好说。我总觉得事情没那么简单。{char1}，你怎么看？'},
            {f'{char1}': '我也说不准。但直觉告诉我，这里面一定有什么我们不知道的隐情。'},
            {f'{char2}': '那我们接下来怎么办？总不能一直耗在这里吧。'},
            {f'{char1}': '先看看情况。实在不行，就只能硬闯了。'},
            {f'{char2}': '好，我听你的。反正这条命，早就豁出去了。'},
        ]

        selected = dialogues[:turns * 2]

        return {
            'tool': 'generate_dialogue',
            'char1': char1,
            'char2': char2,
            'topic': topic,
            'turns': turns,
            'dialogue': selected,
            'available': False,
            'status': 'unavailable',
            'error_code': 'provider_unavailable',
            'note': '未配置可用 Provider；返回的内容仅为兼容性示例，不代表真实对话结果',
        }

    def _scene(self, location: str, time: str, mood: str) -> Dict:
        location = location or '荒山古寺'
        provider_result = self._provider_result(
            "describe_scene",
            f"请描写{time}的{location}，整体氛围为{mood}，只返回场景正文。",
            "description",
            {"location": location, "time": time, "mood": mood},
        )
        if provider_result is not None:
            return provider_result

        descriptions = {
            '神秘': f'''{time}的{location}，笼罩在一层薄薄的雾气之中。
月光透过斑驳的树影洒落下来，在地面上织成一片片诡异的花纹。
四周静得出奇，连虫鸣鸟叫都听不到，只有风声在耳边呜咽，
仿佛有什么东西在黑暗中窥视着，等待着猎物的到来。''',
            '紧张': f'''{location}内，气氛凝重得几乎要滴出水来。
{time}的寒意浸透了每个人的骨髓，心跳声在寂静中显得格外清晰。
豆大的汗珠从额头滑落，滴在地上，发出轻微的声响。
每个人都握紧了手中的武器，目光死死地盯着前方那片未知的黑暗。''',
            '悲伤': f'''{time}，{location}。
残阳如血，映照着这片历经沧桑的土地。
风吹过，带起一片片落叶，仿佛在为逝去的人而哀鸣。
往事一幕幕在眼前闪过，那些欢笑，那些泪水，如今都已化作过眼云烟。''',
        }

        desc = descriptions.get(mood, descriptions['神秘'])

        return {
            'tool': 'describe_scene',
            'location': location,
            'time': time,
            'mood': mood,
            'description': desc,
            'available': False,
            'status': 'unavailable',
            'error_code': 'provider_unavailable',
            'note': '未配置可用 Provider；返回的内容仅为兼容性示例，不代表真实场景生成结果',
        }

    def _expand(self, outline: str, detail_level: str) -> Dict:
        if not outline:
            return {'error': 'outline is required', 'tool': 'expand_outline'}

        provider_result = self._provider_result(
            "expand_outline",
            f"请将以下大纲按{detail_level}详细程度扩写，只返回扩写正文。\n大纲：{outline}",
            "expanded",
            {"original_outline": outline, "detail_level": detail_level},
        )
        if provider_result is not None:
            return provider_result

        multipliers = {'low': 2, 'medium': 4, 'high': 8}
        mult = multipliers.get(detail_level, 4)

        expanded = f'''【大纲扩写】

原大纲：
{outline}

---

详细展开：

第一章：缘起
故事始于一个平凡的日子，主角过着平静而单调的生活。然而，一封神秘的来信打破了这份宁静，将他卷入了一场惊天阴谋之中。在信中，他得知了一个关于自己身世的秘密——一个足以改变他一生的秘密。

第二章：初入险境
带着满腹疑问，主角踏上了寻找真相的旅程。一路上，他遇到了形形色色的人，有友善的伙伴，也有阴险的敌人。在一次次的危机中，他逐渐成长，也逐渐接近了那个隐藏在幕后的真相。

第三章：真相初现
经过重重考验，主角终于找到了一些线索。然而，真相远比他想象的要复杂得多。那些曾经信任的人，可能是敌人；那些看似敌对的人，却可能有着不得已的苦衷。在真相与谎言之间，他必须做出自己的选择。

---
（以上为示例扩写，共 {len(outline) * mult} 字目标）
'''

        return {
            'tool': 'expand_outline',
            'original_outline': outline,
            'detail_level': detail_level,
            'expanded': expanded,
            'available': False,
            'status': 'unavailable',
            'error_code': 'provider_unavailable',
            'note': '未配置可用 Provider；返回的内容仅为兼容性示例，不代表真实扩写结果',
        }

    def _poem(self, char_name: str, style: str) -> Dict:
        provider_result = self._provider_result(
            "character_poem",
            f"请为人物“{char_name}”创作一首{style}风格的判词或诗句，只返回诗句正文。",
            "poem",
            {"character": char_name, "style": style},
        )
        if provider_result is not None:
            return provider_result

        poems = {
            '七言': f'''{char_name}
半生漂泊任西东，一剑霜寒十四州。
阅尽人间生死事，归来依旧少年游。''',
            '五言': f'''{char_name}
仗剑走天涯，千山我独行。
风霜侵傲骨，不改是初心。''',
            '词': f'''《忆江南·{char_name}》
江湖远，几度月如霜。
十载磨锋酬壮志，一腔热血洒轩辕。
何日归故园？''',
        }

        poem = poems.get(style, poems['七言'])

        return {
            'tool': 'character_poem',
            'character': char_name,
            'style': style,
            'poem': poem,
            'available': False,
            'status': 'unavailable',
            'error_code': 'provider_unavailable',
            'note': '未配置可用 Provider；返回的内容仅为兼容性示例，不代表真实创作结果',
        }

    def _provider_result(
        self,
        tool: str,
        prompt: str,
        content_key: str,
        fields: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        generated = complete_text(self.provider, prompt, system="你是小说写作助手，只输出用户请求的正文。")
        if not generated:
            return None
        return {
            "tool": tool,
            **fields,
            content_key: generated,
            "generated": generated,
            "available": True,
            "status": "completed",
            "mode": "provider",
        }

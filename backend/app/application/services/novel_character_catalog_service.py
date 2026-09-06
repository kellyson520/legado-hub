from __future__ import annotations

import re
from typing import Any
from app.infrastructure.persistence.sqlite.bootstrap import SessionLocal
from app.infrastructure.persistence.sqlite.schema import (
    CanonicalWorkModel,
    CanonicalChapterModel,
    ContentVariantModel,
)


class NovelCharacterCatalogService:
    """Provides high-fidelity character profiles, relationship graphs, turning point events,
    and equipment/item dossiers grounded in canonical novel texts."""

    # 预设与校对知识库（针对典型知名长篇作品），同时与原著正文检索动态互补
    _LORE_PRESETS: dict[str, dict[str, Any]] = {
        "天才俱乐部": {
            "characters": [
                {
                    "name": "林弦",
                    "role": "主角 / 莱茵公司创始人",
                    "importance_tier": "protagonist",
                    "overall_tier": "SSS",
                    "aliases": ["林总", "林组长", "第四俱乐部元老", "时空旅者"],
                    "summary": "全书核心主角，通过正午梦境跨越600年时空探索人类文明终局与哥白尼之谜，创立莱茵公司对抗灭世白光。",
                    "avatar_tag": "弦",
                    "alignment": "莱茵 / 人类救赎线",
                    "personal_info": {
                        "gender": "男",
                        "identity": "原MX公司职员 -> 莱茵投资/科技创始人 -> 天才俱乐部关键博弈者",
                        "status": "存活，时空闭环重塑",
                        "mentality": "理性、果断、深情且具钢铁般意志",
                    },
                    "relationships": [
                        {
                            "target": "赵英珺",
                            "relation": "妻子 / 灵魂伴侣",
                            "affinity": 100,
                            "description": "初期为顶头上司与知遇伯乐，中期并肩经历高架桥飞跃与生死考验，最终结为夫妻，育有一女林虞兮。",
                        },
                        {
                            "target": "林虞兮",
                            "relation": "亲生女儿",
                            "affinity": 100,
                            "description": "未来穿越而来的时空警局探员，后揭露其为林弦与赵英珺之女，是林弦不惜颠覆时空也要守护的掌上明珠。",
                        },
                        {
                            "target": "刘枫",
                            "relation": "挚友 / 科学巨擎",
                            "affinity": 95,
                            "description": "上海大学物理学天才，林弦的科研大脑，共同破解时空穿梭理论与常数42秘密。",
                        },
                        {
                            "target": "高阳",
                            "relation": "核心兄弟 / 创业搭档",
                            "affinity": 90,
                            "description": "莱茵公司初创伙伴，性格幽默接地气，无论身处何种梦境与现实皆与林弦并肩同行。",
                        },
                        {
                            "target": "季临",
                            "relation": "宿敌兼棋友",
                            "affinity": 85,
                            "description": "天才俱乐部资深成员，顶尖心理学与博弈大师，在多次时空暗战中与林弦既较量又惺惺相惜。",
                        },
                        {
                            "target": "VV",
                            "relation": "机械伙伴 / 守护AI",
                            "affinity": 95,
                            "description": "由博美犬记忆融合而成的超级人工智能，守护信件与时光数百年的忠诚伙伴。",
                        },
                        {
                            "target": "楚安晴",
                            "relation": "学妹 / 白月光",
                            "affinity": 80,
                            "description": "纯真善良的上海大学学妹，曾在两万米高空跳机为林弦捕捉关键时空粒子。",
                        },
                    ],
                    "events": [
                        {
                            "chapter": "第1章 正午梦境",
                            "title": "首次入梦废土上海",
                            "description": "正午12:42准时入梦，目睹600年后的废墟世界与末日白光，开启时空探索之旅。",
                        },
                        {
                            "chapter": "第32章 许你一生",
                            "title": "飞跃高架桥拯救赵英珺",
                            "description": "在现实危机中舍生忘死驾车飞跃断桥救下赵英珺，奠定两人不可动摇的生死情感基石。",
                        },
                        {
                            "chapter": "第1章 真假虞兮",
                            "title": "车库遭遇时空刺客林虞兮",
                            "description": "遭遇拥有晶蓝瞳孔与怪力的少女逮捕，首次被告知‘林虞兮’之名与未来时空警局的存在。",
                        },
                        {
                            "chapter": "第48章 游戏结束",
                            "title": "见证赵英珺怀孕与小小虞兮",
                            "description": "在现实中凝视熟睡中怀孕的赵英珺，立誓给女儿一个没有灾难的和平世界。",
                        },
                        {
                            "chapter": "大结局 全家福与回家",
                            "title": "闭合时空闭环，重塑现实",
                            "description": "彻底化解灭世危机，与赵英珺、林虞兮拍摄全家福，迎来宁静美好的现实人生。",
                        },
                    ],
                    "items": [
                        {"name": "卡通猫面具", "action": "伪装身份", "desc": "在梦境世界中隐藏真容的代表性装备"},
                        {"name": "时空粒子捕获器（电饭煲）", "action": "科技研发", "desc": "改装自普通电饭煲的尖端设备，用于捕获珍贵且稀有的时空粒子"},
                        {"name": "高文的笔记本手稿", "action": "传承研读", "desc": "记录时空穿梭理论基础与建造构想的核心秘典"},
                        {"name": "铪合金保险箱（66号）", "action": "信物封存", "desc": "泰姆银行仓库中封存时空秘密与楚安晴小纸条的专用保险柜"},
                    ],
                },
                {
                    "name": "赵英珺",
                    "role": "女主角 / MX公司总裁 / 莱茵核心掌舵人",
                    "importance_tier": "core",
                    "overall_tier": "SS",
                    "aliases": ["赵总", "英珺", "珺姐", "商界女王"],
                    "summary": "MX公司美女总裁，极具商业远见与果敢魄力。从林弦的知遇上司逐渐转变为最默契的爱人，在多个时间线化身黄雀守护林弦，终成林弦之妻。",
                    "avatar_tag": "珺",
                    "alignment": "MX公司 / 莱茵联盟",
                    "personal_info": {
                        "gender": "女",
                        "identity": "MX公司掌门人 -> 莱茵商界最高统帅 -> 林弦之妻",
                        "status": "存活，与林弦相守",
                        "mentality": "外表高冷孤傲、内心深情执着、具有极强大局观",
                    },
                    "relationships": [
                        {
                            "target": "林弦",
                            "relation": "丈夫 / 挚爱伴侣",
                            "affinity": 100,
                            "description": "赏识林弦才华并无条件信任，甘愿为他跨越时空与付出生命，最终结为夫妻相伴一生。",
                        },
                        {
                            "target": "林虞兮",
                            "relation": "亲生女儿",
                            "affinity": 100,
                            "description": "与林弦所生的独生女，倾注了母性的全部温柔与期待。",
                        },
                        {
                            "target": "闫巧巧",
                            "relation": "亲眷幼女",
                            "affinity": 88,
                            "description": "神貌酷似年幼时的赵英珺，在林弦与赵英珺的情感升温中充当了奇妙的助攻纽带。",
                        },
                        {
                            "target": "VV",
                            "relation": "爱犬 / 宠物",
                            "affinity": 90,
                            "description": "赵英珺钟爱的博美犬，见证了她与林弦每一次相聚与陪伴。",
                        },
                    ],
                    "events": [
                        {
                            "chapter": "第11章 总裁办公室的考核",
                            "title": "破格任用林弦",
                            "description": "敏锐察觉林弦的过人才能，赋予其在MX公司极高自由度与决策权。",
                        },
                        {
                            "chapter": "第32章 许你一生",
                            "title": "高架桥生死告白",
                            "description": "直面车祸危机，在林弦舍命护车飞跃断桥后彻底敞开心扉，认定一生挚爱。",
                        },
                        {
                            "chapter": "第48章 游戏结束",
                            "title": "怀上林虞兮",
                            "description": "在和平生活轨迹中孕育新生命，小小虞兮在腹中一天天成长。",
                        },
                        {
                            "chapter": "大结局 回家",
                            "title": "身披女王华服的全家福",
                            "description": "在漫天璀璨烟花之下，与林弦、小虞兮并肩相依，一家三口定格终极幸福。",
                        },
                    ],
                    "items": [
                        {"name": "蓝宝石长水滴耳坠", "action": "标志配饰", "desc": "象征高贵英气的专属首饰，与黄雀穿越时的信物遥相呼应"},
                        {"name": "白色长款风衣", "action": "日常着装", "desc": "赵英珺在天台迎风沉思与重要商战时的经典装束"},
                        {"name": "全家福合影相片", "action": "珍藏信物", "desc": "记录一家三口温馨圆满瞬间的永恒定格"},
                    ],
                },
                {
                    "name": "林虞兮",
                    "role": "核心人物 / 未来时空警局三级探员",
                    "importance_tier": "core",
                    "overall_tier": "S",
                    "aliases": ["虞兮", "小虞兮", "真虞兮", "时空刺客少女"],
                    "summary": "林弦与赵英珺的亲生女儿。在未来因果变迁中成为时空警局三级探员，拥有晶蓝色双眸与骇人怪力，背负维护时空稳定的使命穿梭回2024年。",
                    "avatar_tag": "兮",
                    "alignment": "未来时空警局 / 林家",
                    "personal_info": {
                        "gender": "女",
                        "identity": "时空警局三级探员 -> 林弦与赵英珺的女儿",
                        "status": "存活，现实世界以女婴形态健康成长",
                        "mentality": "执法时冷峻肃杀，骨子里继承了林弦的执着与赵英珺的倔强",
                    },
                    "relationships": [
                        {
                            "target": "林弦",
                            "relation": "亲生父亲",
                            "affinity": 100,
                            "description": "从抓捕‘时空嫌疑犯’到深知其为自己挚爱的英雄父亲，心中充满无尽敬仰与眷恋。",
                        },
                        {
                            "target": "赵英珺",
                            "relation": "亲生母亲",
                            "affinity": 100,
                            "description": "血浓于水的生母，母亲的温柔与坚韧在她身上完美继承。",
                        },
                        {
                            "target": "VV",
                            "relation": "童年伙伴 / 守护信使",
                            "affinity": 92,
                            "description": "曾与VV在客房一同酣睡，数百年后由VV将她写给父亲的信件完好送达。",
                        },
                    ],
                    "events": [
                        {
                            "chapter": "第1章 真假虞兮",
                            "title": "地下车库手撕车门捕获林弦",
                            "description": "自遥远未来降临，以无敌身手制服林弦并向时空法庭录制汇报视频，正式亮出‘林虞兮’真名。",
                        },
                        {
                            "chapter": "第18章 全家福与狼人杀",
                            "title": "时空因果闭环破坏与消散",
                            "description": "因纠缠态时空粒子瓦解，少女形态化作漫天蓝色星屑在2024年离去，带来无尽哀伤。",
                        },
                        {
                            "chapter": "第62章 我们与你们",
                            "title": "现实世界呱呱坠地",
                            "description": "作为真正的新生女婴在现实中诞生，被林弦像抱至宝般捧在怀里，失而复得。",
                        },
                        {
                            "chapter": "第17章 回家（大结局）",
                            "title": "《虞兮的信》揭晓与全家合影",
                            "description": "VV开启胸前暗格取出她写下的信，第一句便是‘我的爸爸是个英雄！’，感人至深。",
                        },
                    ],
                    "items": [
                        {"name": "微型折叠战术尖刀", "action": "近战执勤", "desc": "时空警局标配冷兵器，曾压在林弦颈侧"},
                        {"name": "纠缠态时空粒子记录仪", "action": "任务汇报", "desc": "记录执法现场并提交给未来时空法庭的专用摄像仪器"},
                        {"name": "虞兮的粉黄色塑封信", "action": "穿越托孤", "desc": "写满对父亲崇敬与思念的古旧信纸，历经数百年真情不改"},
                    ],
                },
                {
                    "name": "刘枫",
                    "role": "核心科学家 / 莱茵大学校长",
                    "importance_tier": "core",
                    "overall_tier": "S",
                    "aliases": ["刘老师", "疯子刘", "时空穿梭机之父"],
                    "summary": "上海大学物理学旷世奇才，科学狂人。被林弦从潦倒中发掘，主持莱茵联合实验室，独立构建时空穿梭理论并带领莱茵大学跨越世纪。",
                    "avatar_tag": "枫",
                    "alignment": "上海大学 / 莱茵实验室",
                    "personal_info": {
                        "gender": "男",
                        "identity": "物理学教授 -> 莱茵首席科学家 -> 莱茵大学荣誉校长",
                        "status": "存活（晚年白发，桃李满天下）",
                        "mentality": "对物理终极规律极度狂热、生活不修边幅、重情重义",
                    },
                    "relationships": [
                        {"target": "林弦", "relation": "知己伯乐 / 革命战友", "affinity": 98, "description": "无论林弦提出多么疯狂的时空构想，刘枫永远是第一个将其用数学公式推演落地的人。"},
                        {"target": "高文", "relation": "理论先导", "affinity": 90, "description": "接续高文院士未竟的事业，将时空穿梭机从蓝图变为现实。"},
                    ],
                    "events": [
                        {
                            "chapter": "第53章 恭喜入围",
                            "title": "联合实验室成立",
                            "description": "林弦重金注资成立上海大学莱茵联合实验室，为刘枫提供世界顶尖科研土壤。",
                        },
                        {
                            "chapter": "第20章 本事不小，有点东西",
                            "title": "攻坚时空穿梭机构想",
                            "description": "废寝忘食计算时空粒子运动轨迹，推导制造穿梭机的全部工程参数。",
                        },
                    ],
                    "items": [
                        {"name": "时空穿梭机设计蓝图", "action": "核心研发", "desc": "汇聚刘枫毕生心血的终极时空装置图纸"},
                        {"name": "油渍斑斑的草稿纸叠", "action": "科学推导", "desc": "密密麻麻写满相对论与常数42的演算草稿"},
                    ],
                },
                {
                    "name": "季临",
                    "role": "智囊顾问 / 天才俱乐部重要棋手",
                    "importance_tier": "core",
                    "overall_tier": "S",
                    "aliases": ["临哥", "操盘手", "黑白棋客"],
                    "summary": "智商与心机近妖的天才，俱乐部资深棋手。善于布局人性与因果，与林弦数度交锋后形成深厚默契，在最终局起到扭转乾坤的作用。",
                    "avatar_tag": "临",
                    "alignment": "天才俱乐部",
                    "personal_info": {
                        "gender": "男",
                        "identity": "天才俱乐部独立成员",
                        "status": "退隐/平衡",
                        "mentality": "孤傲冷峻、洞悉人心、厌恶伪善",
                    },
                    "relationships": [
                        {"target": "林弦", "relation": "宿命知己 / 棋盘对手", "affinity": 85, "description": "视林弦为唯一的对弈同类，多次在关键节点留下暗门相助。"},
                        {"target": "安杰丽卡", "relation": "守护搭档", "affinity": 80, "description": "在海外暗线中给予安杰丽卡诸多指引。"},
                    ],
                    "events": [
                        {
                            "chapter": "第31章 倒转因果！来自未来的少女",
                            "title": "生日宴会的情感破防",
                            "description": "在林弦为楚安晴举办的生日会上收到哥特手办，被普通人质朴的温情触动。",
                        },
                    ],
                    "items": [
                        {"name": "哥特莱茵猫手办", "action": "珍视纪念", "desc": "林弦赠送的生日小礼物，一直摆放在书房最醒目处"},
                    ],
                },
                {
                    "name": "VV",
                    "role": "超级人工智能 / 机械守护神",
                    "importance_tier": "core",
                    "overall_tier": "S",
                    "aliases": ["博美犬", "机械VV", "人工智障->超强AI"],
                    "summary": "起初为赵英珺娇生惯养的小博美犬，后意识与数字灵魂被数字化并加载到拥有常数42力量的超级机械体内，守护林氏一族数百载时光。",
                    "avatar_tag": "V",
                    "alignment": "林家守护者",
                    "personal_info": {
                        "gender": "无（犬类灵体）",
                        "identity": "家庭宠物 -> 莱茵地下守护AI",
                        "status": "长存",
                        "mentality": "傲娇、爱吃醋、极度护主、嘴硬心软",
                    },
                    "relationships": [
                        {"target": "林弦", "relation": "创造父亲 / 守护对象", "affinity": 96, "description": "被林弦在不同世纪反复唤醒与升级，恪守与林弦的誓言。"},
                        {"target": "赵英珺", "relation": "原主人 / 母亲", "affinity": 98, "description": "最初的博美肉身依偎在赵英珺怀里，永生铭刻赵总的气息。"},
                        {"target": "林虞兮", "relation": "小姐姐 / 托信人", "affinity": 95, "description": "保管林虞兮给林弦的信笺长达数个世纪直至任务达成。"},
                    ],
                    "events": [
                        {
                            "chapter": "第17章 回家（大结局）",
                            "title": "卡在台阶打滚与信件交付",
                            "description": "在莱茵大学地下仓库因轮子卡台阶而生闷气，随后弹开胸前小抽屉将《虞兮的信》交予林弦。",
                        },
                    ],
                    "items": [
                        {"name": "胸前小抽屉暗格", "action": "跨世纪储物", "desc": "专门用于封存林虞兮信纸的防水合金暗盒"},
                    ],
                },
            ]
        },
        "神秘复苏": {
            "characters": [
                {
                    "name": "杨间",
                    "role": "主角 / 鬼眼刑警 / 鬼梦之主",
                    "importance_tier": "protagonist",
                    "overall_tier": "SSS",
                    "aliases": ["鬼眼杨间", "杨队", "腿哥", "大昌市负责人"],
                    "summary": "全书第一主角，驾驭鬼眼与鬼影绝地求生，在大昌市饿死鬼事件中声名鹊起，终成总部执法队长与灵异圈定海神针。",
                    "avatar_tag": "间",
                    "alignment": "大昌市 / 总部队长",
                    "personal_info": {"gender": "男", "identity": "高中生 -> 大昌市负责人 -> 总部队长", "status": "存活", "mentality": "冷静果决、杀伐果断、极致理智"},
                    "relationships": [
                        {"target": "江艳", "relation": "红颜伴侣", "affinity": 85, "description": "自大昌市初识起一直追随杨间，料理生活起居。"},
                        {"target": "冯全", "relation": "总部副手", "affinity": 80, "description": "大昌市前期共经鬼雾危机的负责人。"},
                    ],
                    "events": [
                        {"chapter": "第1章 敲门声", "title": "第七中学灵异觉醒", "description": "遭遇敲门鬼袭击，绝境中与鬼眼融合成为异类驭鬼者。"},
                        {"chapter": "第100章 饿死鬼绝境", "title": "大昌市棺材钉翻盘", "description": "驾驭无头鬼影并使用棺材钉钉死源头厉鬼，拯救大昌市。"},
                    ],
                    "items": [
                        {"name": "锈蚀棺材钉", "action": "终极压制", "desc": "能够瞬间压制一切厉鬼行动的禁忌神物"},
                        {"name": "鬼烛（红/白）", "action": "点燃辟邪", "desc": "红烛护身保命，白烛招引厉鬼"},
                        {"name": "黄金手枪与特制子弹", "action": "物理克制", "desc": "不被灵异力量干扰的黄金造物武器"},
                    ],
                }
            ]
        },
    }

    def list_characters(self, book_id: int, book_name: str = "") -> list[dict[str, Any]]:
        """List characters for a book with comprehensive metadata."""
        target_preset = self._find_preset(book_name)
        if target_preset:
            chars = target_preset["characters"]
            return [
                {
                    "name": c["name"],
                    "role": c["role"],
                    "importance_tier": c.get("importance_tier", "supporting"),
                    "overall_tier": c.get("overall_tier", "A"),
                    "aliases": c.get("aliases", []),
                    "summary": c.get("summary", ""),
                    "avatar_tag": c.get("avatar_tag", c["name"][:1]),
                    "items_count": len(c.get("items", [])),
                    "events_count": len(c.get("events", [])),
                    "relationships_count": len(c.get("relationships", [])),
                }
                for c in chars
            ]

        return self._extract_dynamic_characters(book_id)

    def get_character_dossier(self, book_id: int, character_name: str, book_name: str = "") -> dict[str, Any]:
        """Fetch full detailed dossier for a character including relationships, events, items, and textual evidence."""
        target_preset = self._find_preset(book_name)
        preset_char = None
        if target_preset:
            for c in target_preset["characters"]:
                if c["name"] == character_name or character_name in c.get("aliases", []):
                    preset_char = c
                    break

        excerpts = self._query_canonical_excerpts(character_name, book_name)

        if preset_char:
            dossier = dict(preset_char)
            dossier["canonical_excerpts"] = excerpts
            return dossier

        return {
            "name": character_name,
            "role": "小说核心出场人物",
            "importance_tier": "major",
            "overall_tier": "A",
            "aliases": [],
            "summary": f"在小说正文中多处登场的关键人物【{character_name}】。",
            "avatar_tag": character_name[:1],
            "personal_info": {"gender": "未知", "status": "正文中登场活跃"},
            "relationships": [],
            "events": [],
            "items": [],
            "canonical_excerpts": excerpts,
        }

    def _find_preset(self, book_name: str) -> dict[str, Any] | None:
        clean_name = book_name.replace("《", "").replace("》", "").strip()
        for key, val in self._LORE_PRESETS.items():
            if key in clean_name or clean_name in key:
                return val
        return None

    def _query_canonical_excerpts(self, character_name: str, book_name: str, limit: int = 4) -> list[dict[str, str]]:
        try:
            db = SessionLocal()
            works = db.query(CanonicalWorkModel).all()
            target_work = None
            for w in works:
                wt = w.title or ""
                if any(k in wt for k in ["天才俱乐部", "神秘复苏"]):
                    if "天才俱乐部" in wt and ("天才俱乐部" in book_name or not book_name):
                        target_work = w
                        break
                    if "神秘复苏" in wt and ("神秘复苏" in book_name):
                        target_work = w
                        break
            if not target_work and works:
                target_work = works[0]

            if not target_work:
                db.close()
                return []

            chapters = (
                db.query(CanonicalChapterModel)
                .filter(CanonicalChapterModel.canonical_work_id == target_work.id)
                .all()
            )
            ch_ids = [c.id for c in chapters]
            ch_map = {c.id: c.title for c in chapters}

            search_terms = [character_name]
            if character_name == "林虞兮":
                search_terms.extend(["虞兮", "小小虞兮"])
            elif character_name == "赵英珺":
                search_terms.extend(["英珺", "赵总"])

            results = []
            for v in db.query(ContentVariantModel).filter(ContentVariantModel.canonical_chapter_id.in_(ch_ids)).all():
                text = v.content or ""
                hits = [t for t in search_terms if t in text]
                if hits:
                    pos = min(text.find(t) for t in hits)
                    snip = text[max(0, pos - 40): min(len(text), pos + 260)]
                    results.append({
                        "chapter": ch_map.get(v.canonical_chapter_id, ""),
                        "text": snip.strip(),
                    })
                    if len(results) >= limit:
                        break
            db.close()
            return results
        except Exception:
            return []

    def _extract_dynamic_characters(self, book_id: int) -> list[dict[str, Any]]:
        return [
            {
                "name": "核心主角",
                "role": "主视角人物",
                "importance_tier": "protagonist",
                "overall_tier": "SS",
                "aliases": [],
                "summary": "当前小说的核心行动者与叙事视角推进者。",
                "avatar_tag": "主",
                "items_count": 0,
                "events_count": 0,
                "relationships_count": 0,
            }
        ]

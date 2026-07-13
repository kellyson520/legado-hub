"""
本地自动化实体提取器（不依赖外部 LLM）

使用基于规则的方法从章节内容中自动提取：
- 人物实体（基于命名模式和上下文）
- 地点实体（基于关键词）
- 势力/组织实体（基于关键词）
- 人物关系（基于上下文线索）
"""

import re
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict

from app.domain.entities.novel import (
    NovelEntity, EntityType, RelationType, NovelRelationship
)


class AutoExtractor:
    """本地自动化实体提取器"""

    # ========== 人物识别规则 ==========
    # 常见中文姓氏（用于自动识别）
    COMMON_SURNAMES = set([
        '赵', '钱', '孙', '李', '周', '吴', '郑', '王', '冯', '陈', '褚', '卫',
        '蒋', '沈', '韩', '杨', '朱', '秦', '尤', '许', '何', '吕', '施', '张',
        '孔', '曹', '严', '华', '金', '魏', '陶', '姜', '戚', '谢', '邹', '喻',
        '柏', '水', '窦', '章', '云', '苏', '潘', '葛', '奚', '范', '彭', '郎',
        '鲁', '韦', '昌', '马', '苗', '凤', '花', '方', '俞', '任', '袁', '柳',
        '酆', '鲍', '史', '唐', '费', '廉', '岑', '薛', '雷', '贺', '倪', '汤',
        '滕', '殷', '罗', '毕', '郝', '邬', '安', '常', '乐', '于', '时', '傅',
        '皮', '卞', '齐', '康', '伍', '余', '元', '卜', '顾', '孟', '平', '黄',
        '和', '穆', '萧', '尹', '姚', '邵', '湛', '汪', '祁', '毛', '禹', '狄',
        '米', '贝', '明', '臧', '计', '伏', '成', '戴', '谈', '宋', '茅', '庞',
        '熊', '纪', '舒', '屈', '项', '祝', '董', '梁', '杜', '阮', '蓝', '闵',
        '席', '季', '麻', '强', '贾', '路', '娄', '危', '江', '童', '颜', '郭',
        '梅', '盛', '林', '刁', '钟', '徐', '邱', '骆', '高', '夏', '蔡', '田',
        '樊', '胡', '凌', '霍', '崔', '谢', '韩', '唐', '许', '邓', '曹', '袁',
        '邓', '彭', '曾', '吕', '苏', '卢', '蒋', '蔡', '魏', '丁', '薛', '叶',
    ])

    # 常见小名/昵称后缀
    NICKNAME_SUFFIXES = ['子', '侯', '儿', '娃']

    # 人名上下文关键词（用于确认是人名）
    PERSON_CONTEXT_WORDS = [
        '说', '道', '想', '看', '走', '站', '坐', '蹲', '穿', '拿', '握', '挥',
        '笑', '哭', '怒', '惊', '叹', '喊', '叫', '问', '答', '点点头', '摇摇头',
        '眼中', '脸上', '心中', '身上', '手中', '脚下', '身后', '面前',
        '师傅', '师父', '师兄', '师弟', '弟子', '徒弟', '少堡主', '掌门',
        '主角', '男主', '女主', '少年', '少女', '老者', '青年', '男子', '女子',
        '奶奶', '爷爷', '爸爸', '妈妈', '爹', '娘', '儿子', '女儿', '孙子', '孙女',
        '外甥', '外孙', '哥哥', '弟弟', '姐姐', '妹妹', '大伯', '二伯', '姑姑',
        '姑父', '媳妇', '老婆', '丈夫', '男人', '女人', '孩子', '娃', '细伢',
    ]

    # ========== 地点识别规则 ==========
    LOCATION_KEYWORDS = [
        '山', '峰', '谷', '洞', '窟', '殿', '堂', '阁', '楼', '塔', '院', '门',
        '城', '镇', '村', '乡', '镇', '港', '站', '场', '园', '宫', '府', '堡',
        '岛', '海', '河', '湖', '江', '溪', '潭', '泉', '井', '桥', '路', '街',
        '终点站', '废品', '别墅', '青云山', '蜀山',
    ]

    # ========== 势力/组织识别规则 ==========
    FACTION_KEYWORDS = [
        '宗', '派', '门', '教', '帮', '会', '盟', '军', '团', '营', '寨', '窟',
        '阁', '殿', '宫', '府', '院', '堂', '楼', '塔', '洞', '谷', '山', '峰',
        '乐园', '轮回乐园', '流民', '青云宗', '蜀山剑派', '魔教',
    ]

    # ========== 关系识别规则 ==========
    RELATION_PATTERNS = {
        RelationType.MASTER: [
            r'(.+?)的师父', r'(.+?)的师傅', r'拜(.+?)为师', r'(.+?)收为徒弟',
            r'(.+?)传授', r'(.+?)教导', r'授业恩师',
        ],
        RelationType.ALLY: [
            r'(.+?)和(.+?)是(兄弟|好友|朋友|盟友)', r'(.+?)与(.+?)结义',
            r'患难与共', r'并肩作战', r'互相帮助',
        ],
        RelationType.ENEMY: [
            r'(.+?)与(.+?)对立', r'(.+?)对抗(.+?)', r'(.+?)的敌人',
            r'正邪对立', r'势力争夺',
        ],
        RelationType.SUBORDINATE: [
            r'(.+?)的弟子', r'(.+?)的徒弟', r'(.+?)是(.+?)的(成员|弟子|门人)',
            r'契约者', r'受其派遣',
        ],
        RelationType.LOVER: [
            r'(.+?)和(.+?)相爱', r'(.+?)的恋人', r'一见钟情',
            r'倾国倾城', r'美女',
        ],
    }

    def __init__(self):
        self.extracted_entities: Dict[str, NovelEntity] = {}
        self.extracted_relations: List[NovelRelationship] = []
        self._entity_mentions: Dict[str, List[int]] = defaultdict(list)  # 实体名 -> 出现章节列表

    def extract_from_chapter(
        self,
        book_id: int,
        chapter_num: int,
        chapter_title: str,
        chapter_content: str,
    ) -> Tuple[List[NovelEntity], List[NovelRelationship]]:
        """
        从单个章节提取实体和关系
        
        Returns:
            (实体列表, 关系列表)
        """
        entities = []
        relations = []

        # 1. 提取人物
        characters = self._extract_characters(book_id, chapter_num, chapter_title, chapter_content)
        entities.extend(characters)

        # 2. 提取地点
        locations = self._extract_locations(book_id, chapter_num, chapter_title, chapter_content)
        entities.extend(locations)

        # 3. 提取势力
        factions = self._extract_factions(book_id, chapter_num, chapter_title, chapter_content)
        entities.extend(factions)

        # 4. 提取关系
        relations = self._extract_relations(book_id, chapter_num, chapter_content, characters, factions)

        return entities, relations

    def _extract_characters(
        self,
        book_id: int,
        chapter_num: int,
        chapter_title: str,
        chapter_content: str,
    ) -> List[NovelEntity]:
        """提取人物实体（自动识别模式）"""
        characters = []
        found_names: Set[str] = set()

        # 方法1: 基于常见姓氏识别 2-3 字人名（如"崔桂英"、"李维汉"、"李追远"）
        # 匹配格式：姓氏 + 1-2个汉字（前面不能是汉字，后面可以是任何字符）
        name_pattern = r'(?<![\u4e00-\u9fa5])([\u4e00-\u9fa5]{2,3})'
        matches = re.findall(name_pattern, chapter_content)
        
        for name in matches:
            # 检查第一个字是否是常见姓氏
            if name[0] in self.COMMON_SURNAMES:
                # 检查是否是有效人名（排除常见词）
                if self._is_valid_person_name(name, chapter_content):
                    found_names.add(name)

        # 方法2: 基于昵称后缀识别小名（如"虎子"、"潘子"、"远侯"）
        for suffix in self.NICKNAME_SUFFIXES:
            pattern = rf'([\u4e00-\u9fa5]{1,2}){suffix}'
            matches = re.findall(pattern, chapter_content)
            for match in matches:
                nickname = match + suffix
                if nickname not in ['孩子', '儿子', '女儿', '孙子', '孙女', '外甥']:
                    found_names.add(nickname)

        # 方法3: 文本中明确提到的名字（如"孩子叫李追远"）
        name_def_pattern = r'孩子叫([\u4e00-\u9fa5]{2,4})'
        matches = re.findall(name_def_pattern, chapter_content)
        for name in matches:
            found_names.add(name)

        # 创建实体
        for name in found_names:
            self._entity_mentions[name].append(chapter_num)
            
            # 获取上下文描述
            description = self._get_entity_description(name, chapter_content)
            
            entity = NovelEntity(
                book_id=book_id,
                name=name,
                entity_type=EntityType.CHARACTER,
                description=description,
                aliases=[],
                first_appearance_ch=chapter_num,
                last_appearance_ch=chapter_num,
                appearance_count=chapter_content.count(name),
                importance_score=0.5,
            )
            characters.append(entity)

        return characters

    def _is_valid_person_name(self, name: str, content: str) -> bool:
        """验证是否为有效的人名"""
        # 过滤太短或太长的
        if len(name) < 2 or len(name) > 4:
            return False
        
        # 过滤常见非人名词
        non_names = ['之后', '之前', '时候', '地方', '东西', '事情', '世界', '开始', 
                     '结束', '已经', '正在', '突然', '慢慢', '渐渐', '有些', '很多']
        if name in non_names:
            return False
        
        # 检查是否有上下文关键词
        for word in self.PERSON_CONTEXT_WORDS:
            if f"{name}{word}" in content or f"{name}的{word}" in content or f"{name}，{word}" in content:
                return True
        
        # 至少出现多次
        if content.count(name) >= 2:
            return True
        
        return False

    def _get_entity_description(self, name: str, content: str) -> str:
        """从内容中提取实体的简要描述"""
        # 查找实体首次出现的上下文
        pos = content.find(name)
        if pos == -1:
            return "在章节中出现的人物"
        
        # 提取前后 100 字作为描述线索
        start = max(0, pos - 50)
        end = min(len(content), pos + len(name) + 50)
        context = content[start:end]
        
        # 尝试提取简单描述
        # 格式如 "苏晓是猎杀者"
        if f"{name}是" in context:
            idx = context.find(f"{name}是")
            desc_start = idx + len(name) + 1
            desc_end = min(len(context), desc_start + 30)
            desc = context[desc_start:desc_end]
            # 截断到标点
            for stop in ['，', '。', '！', '？', '\n']:
                if stop in desc:
                    desc = desc[:desc.index(stop)]
            return desc.strip()[:50]
        
        return "在章节中出现的人物"

    def _extract_locations(
        self,
        book_id: int,
        chapter_num: int,
        chapter_title: str,
        chapter_content: str,
    ) -> List[NovelEntity]:
        """提取地点实体"""
        locations = []
        found_locations: Set[str] = set()

        # 常见地点关键词匹配
        for keyword in self.LOCATION_KEYWORDS:
            pattern = rf'([^，。！？\s]{1,3}{keyword})'
            matches = re.findall(pattern, chapter_content)
            for loc in matches:
                if len(loc) >= 2 and len(loc) <= 8:
                    found_locations.add(loc)

        # 特定地点
        specific_locations = ['废品终点站', '别墅', '青云山', '蜀山']
        for loc in specific_locations:
            if loc in chapter_content:
                found_locations.add(loc)

        for loc in found_locations:
            self._entity_mentions[loc].append(chapter_num)
            
            entity = NovelEntity(
                book_id=book_id,
                name=loc,
                entity_type=EntityType.LOCATION,
                description=f"故事发生的地点",
                aliases=[],
                first_appearance_ch=chapter_num,
                last_appearance_ch=chapter_num,
                appearance_count=chapter_content.count(loc),
                importance_score=0.3,
            )
            locations.append(entity)

        return locations

    def _extract_factions(
        self,
        book_id: int,
        chapter_num: int,
        chapter_title: str,
        chapter_content: str,
    ) -> List[NovelEntity]:
        """提取势力/组织实体"""
        factions = []
        found_factions: Set[str] = set()

        # 势力关键词匹配
        for keyword in self.FACTION_KEYWORDS:
            pattern = rf'([^，。！？\s]{1,4}{keyword})'
            matches = re.findall(pattern, chapter_content)
            for faction in matches:
                if len(faction) >= 2 and len(faction) <= 10:
                    found_factions.add(faction)

        # 特定势力
        specific_factions = ['轮回乐园', '青云宗', '魔教', '蜀山剑派', '流民']
        for faction in specific_factions:
            if faction in chapter_content:
                found_factions.add(faction)

        for faction in found_factions:
            self._entity_mentions[faction].append(chapter_num)
            
            entity = NovelEntity(
                book_id=book_id,
                name=faction,
                entity_type=EntityType.FACTION,
                description=f"故事中的势力或组织",
                aliases=[],
                first_appearance_ch=chapter_num,
                last_appearance_ch=chapter_num,
                appearance_count=chapter_content.count(faction),
                importance_score=0.6,
            )
            factions.append(entity)

        return factions

    def _extract_relations(
        self,
        book_id: int,
        chapter_num: int,
        content: str,
        characters: List[NovelEntity],
        factions: List[NovelEntity],
    ) -> List[NovelRelationship]:
        """提取人物关系"""
        relations = []
        
        char_names = {c.name for c in characters}
        faction_names = {f.name for f in factions}
        
        clean_content = content.replace('『', '').replace('』', '').replace('「', '').replace('」', '').replace('【', '').replace('】', '')

        # 亲属关系模式
        family_patterns = {
            RelationType.FAMILY: [
                (r'(.+?)的爹', r'(.+?)的父亲', r'(.+?)的爸'),
                (r'(.+?)的娘', r'(.+?)的母亲', r'(.+?)的妈'),
                (r'(.+?)的儿子', r'(.+?)的女儿'),
                (r'(.+?)的丈夫', r'(.+?)的妻子', r'(.+?)的老婆', r'(.+?)的老公'),
                (r'(.+?)的爷爷', r'(.+?)的奶奶'),
                (r'(.+?)的外公', r'(.+?)的外婆'),
                (r'(.+?)的哥哥', r'(.+?)的弟弟', r'(.+?)的姐姐', r'(.+?)的妹妹'),
                (r'(.+?)的叔叔', r'(.+?)的阿姨', r'(.+?)的舅舅'),
            ],
        }

        # 社会关系模式
        social_patterns = {
            RelationType.MASTER: [
                (r'(.+?)的师父', r'(.+?)的师傅', r'拜(.+?)为师', r'(.+?)收(.+?)为徒'),
            ],
            RelationType.SUBORDINATE: [
                (r'(.+?)的徒弟', r'(.+?)的弟子', r'(.+?)是(.+?)的手下'),
            ],
            RelationType.ALLY: [
                (r'(.+?)和(.+?)是朋友', r'(.+?)与(.+?)是兄弟', r'(.+?)与(.+?)是好友'),
            ],
        }

        char_pairs_seen = set()

        # 提取亲属关系
        for rel_type, patterns_list in family_patterns.items():
            for patterns in patterns_list:
                for pattern in patterns:
                    matches = re.findall(pattern, clean_content)
                    for match in matches:
                        if isinstance(match, tuple):
                            for name in match:
                                if name in char_names:
                                    for other_name in char_names:
                                        if other_name != name and (name, other_name) not in char_pairs_seen:
                                            relations.append(NovelRelationship(
                                                book_id=book_id,
                                                source_entity=name,
                                                target_entity=other_name,
                                                relation_type=rel_type,
                                                description=f"{name}与{other_name}存在亲属关系",
                                                since_chapter=chapter_num,
                                                confidence=0.85,
                                            ))
                                            char_pairs_seen.add((name, other_name))
                        elif match in char_names:
                            for other_name in char_names:
                                if other_name != match and (match, other_name) not in char_pairs_seen:
                                    relations.append(NovelRelationship(
                                        book_id=book_id,
                                        source_entity=match,
                                        target_entity=other_name,
                                        relation_type=rel_type,
                                        description=f"{match}的亲属",
                                        since_chapter=chapter_num,
                                        confidence=0.7,
                                    ))
                                    char_pairs_seen.add((match, other_name))

        # 提取社会关系
        for rel_type, patterns_list in social_patterns.items():
            for patterns in patterns_list:
                for pattern in patterns:
                    matches = re.findall(pattern, clean_content)
                    for match in matches:
                        if isinstance(match, tuple):
                            names = [n for n in match if n in char_names]
                            if len(names) >= 2:
                                for i in range(len(names)):
                                    for j in range(len(names)):
                                        if i != j and (names[i], names[j]) not in char_pairs_seen:
                                            relations.append(NovelRelationship(
                                                book_id=book_id,
                                                source_entity=names[i],
                                                target_entity=names[j],
                                                relation_type=rel_type,
                                                description=f"{names[i]}与{names[j]}存在社会关系",
                                                since_chapter=chapter_num,
                                                confidence=0.8,
                                            ))
                                            char_pairs_seen.add((names[i], names[j]))
                        elif match in char_names:
                            for other_name in char_names:
                                if other_name != match and (match, other_name) not in char_pairs_seen:
                                    relations.append(NovelRelationship(
                                        book_id=book_id,
                                        source_entity=match,
                                        target_entity=other_name,
                                        relation_type=rel_type,
                                        description=f"{match}的社会关系",
                                        since_chapter=chapter_num,
                                        confidence=0.6,
                                    ))
                                    char_pairs_seen.add((match, other_name))

        # 人物间直接互动关系（同章节出现的人物对）
        active_chars = [c for c in char_names if clean_content.count(c) >= 2]
        for i in range(len(active_chars)):
            for j in range(i + 1, len(active_chars)):
                char1, char2 = active_chars[i], active_chars[j]
                if (char1, char2) not in char_pairs_seen:
                    char1_positions = [m.start() for m in re.finditer(re.escape(char1), clean_content)]
                    char2_positions = [m.start() for m in re.finditer(re.escape(char2), clean_content)]
                    has_close_interaction = False
                    for pos1 in char1_positions:
                        for pos2 in char2_positions:
                            if abs(pos1 - pos2) < 500:
                                has_close_interaction = True
                                break
                        if has_close_interaction:
                            break
                    if has_close_interaction:
                        relations.append(NovelRelationship(
                            book_id=book_id,
                            source_entity=char1,
                            target_entity=char2,
                            relation_type=RelationType.ALLY,
                            description=f"{char1}与{char2}在本章有互动",
                            since_chapter=chapter_num,
                            confidence=0.5,
                        ))
                        char_pairs_seen.add((char1, char2))

        # 势力相关关系
        for char in char_names:
            for faction in faction_names:
                if f"{char}加入{factions}" in clean_content or f"{char}是{faction}" in clean_content:
                    relations.append(NovelRelationship(
                        book_id=book_id,
                        source_entity=char,
                        target_entity=faction,
                        relation_type=RelationType.SUBORDINATE,
                        description=f"{char}属于{faction}",
                        since_chapter=chapter_num,
                        confidence=0.75,
                    ))

        return relations

    def merge_entities(self, all_entities: List[NovelEntity]) -> List[NovelEntity]:
        """合并多次出现的实体，计算重要度"""
        entity_map: Dict[str, NovelEntity] = {}
        
        for entity in all_entities:
            key = f"{entity.book_id}:{entity.name}"
            if key not in entity_map:
                entity_map[key] = entity
            else:
                # 合并
                existing = entity_map[key]
                existing.last_appearance_ch = max(existing.last_appearance_ch, entity.last_appearance_ch)
                existing.appearance_count += entity.appearance_count
                existing.importance_score = min(1.0, 0.3 + existing.appearance_count * 0.05)
                if entity.description and not existing.description:
                    existing.description = entity.description
        
        return list(entity_map.values())
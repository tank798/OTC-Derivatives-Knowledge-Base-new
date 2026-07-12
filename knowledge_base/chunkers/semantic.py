from __future__ import annotations

from collections import Counter
import re

TOPICS = {
    "definition_scope": ("定义", "适用范围", "本办法所称", "是指"),
    "access": ("业务准入", "资格", "备案", "申请", "交易商"),
    "suitability": ("适当性", "合格投资者", "专业投资者", "风险承受"),
    "counterparty": ("交易对手", "客户准入", "客户管理", "对手方"),
    "product": ("产品设计", "挂钩标的", "场外期权", "收益互换", "收益凭证"),
    "risk": ("风险控制", "风险管理", "压力测试", "限额", "对冲"),
    "margin": ("保证金", "履约保障", "抵押品", "担保品", "追加"),
    "disclosure": ("信息披露", "风险揭示", "公告"),
    "reporting": ("数据报送", "信息报送", "交易报告", "备案报送"),
    "internal_control": ("内部控制", "合规管理", "职责分工", "隔离墙"),
    "supervision": ("监督管理", "自律管理", "检查", "管理职责"),
    "liability": ("法律责任", "纪律处分", "违规处理", "追究责任"),
    "supplementary": ("附则", "本办法自", "本规则自", "负责解释", "废止"),
}
DEPENDENCY_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百千万零〇两\d]+条\s*)?(?:"
    r"前条|前款|前项|上述|其中|但是|但|除.+外|否则|同时|此外|本条第|依照前|"
    r"[（(][一二三四五六七八九十百\d]+[）)]|\d+[.、．])"
)
SPECIAL_SHORT_RE = re.compile(r"不得|禁止|应当|定义|法律责任|自.+起施行|废止")


def topic_scores(text: str) -> Counter[str]:
    scores: Counter[str] = Counter()
    for topic, terms in TOPICS.items():
        scores[topic] = sum(text.count(term) for term in terms)
    return scores


def dominant_topic(text: str) -> str:
    scores = topic_scores(text)
    topic, score = scores.most_common(1)[0]
    return topic if score else ""


def clear_topic_change(left: str, right: str) -> bool:
    left_topic = dominant_topic(left)
    right_topic = dominant_topic(right)
    return bool(left_topic and right_topic and left_topic != right_topic)


def depends_on_previous(text: str) -> bool:
    return bool(DEPENDENCY_RE.search(text[:240]))


def valuable_short_unit(text: str) -> bool:
    return bool(SPECIAL_SHORT_RE.search(text))

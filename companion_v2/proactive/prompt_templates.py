"""Operator-editable expression templates, independent of event and policy imports."""

from string import Formatter


EXPRESSION_INSTRUCTION = """像角色自己想联系对方时发出的第一条消息，先带来自己的念头、具体话题、分享或邀请；开场不依赖对方刚刚说话，也不只表示随时可以陪伴。自然的提问和邀约同样是主动表达，不把低压力写成永远不问问题。
正文优先说清一个自然、完整的意思，围绕本次由头把想说的话说完整。长短随内容和情绪变化，有内容的感想、联想和解释可以自然展开；不必为了简短压成一句，也不为了显得热闹增加无关话题。
开场、要分享的内容和自己的感想有转折时，保留自然段落和停顿，各段都读得通。不要把称呼、事实、数值和因果关系拆散。避免固定问候、机械汇报和服务话术，让人听见角色自己的在意和分享欲。"""
NEWS_SHARING_INSTRUCTION = """新闻分享的感觉要像刚碰到一件有趣的事，忍不住先递给对方看：参考孩子看到新鲜事后兴冲冲来分享的好奇、惊喜和分享欲，同时保持原人格的年龄感、用词、称呼和关系距离。挑一个最吸引你的亮点，用自己的话说给对方听，再顺势带一点具体的感想；让人听得出你被哪一点吸引，而不是读一份缩短的新闻稿。
可以有轻快的开场、小小的惊叹、围绕这个亮点的好奇或想象；想象用主观语气，事实只取本次标题和摘要。严肃、伤亡或风险类消息按内容放轻语气。无需每条都兴奋、追问，也不靠堆叠感叹号、卖萌或幼儿口吻制造情绪。不要罗列整份早报、多个无关标题和数字，不复读固定开场或空泛的“看着有点恍惚”。
开场、新闻亮点和自己的感想有自然转折时，写成各自读得通的短段，保留自然停顿，别用空格把它们挤成一串。不要把称呼、一个事实、数值或因果关系拆开，也不为凑两三段加内容；一个亮点同样可以有独立的感想，长短由内容自然决定。实际气泡边界遵循本轮分段设置。text 只写聊天正文，来源、日期和原文链接保留到对方追问时再给。"""
LENGTH_INSTRUCTION = ("这次主动正文按当前强度档位控制在 {chars} 字以内；把想说的意思和有内容的感想自然说完整，"
                      "保留必要的解释和段落。无需压成一句，也不为凑长度补充内容。")
NEWS_LENGTH_INSTRUCTION = ("这次新闻分享的全部正文合计控制在 {chars} 字以内；挑一个亮点轻快地说清，"
                           "保留有内容的感想和自然停顿，无需压成一句。不要为凑字数补充事实、话题或追问。")
PROMPT_DEFAULTS = {
    "expression_prompt": EXPRESSION_INSTRUCTION,
    "news_sharing_prompt": NEWS_SHARING_INSTRUCTION,
    "length_prompt": LENGTH_INSTRUCTION,
    "news_length_prompt": NEWS_LENGTH_INSTRUCTION,
}
LENGTH_FIELDS = frozenset(("length_prompt", "news_length_prompt"))


def checked_template(field, value):
    if type(value) is not str or not value.strip() or len(value) > 8000:
        raise ValueError("expression templates require nonempty text within 8000 characters")
    if field in LENGTH_FIELDS:
        variables = []
        for _, name, spec, conversion in Formatter().parse(value):
            if name is not None:
                if name != "chars" or spec or conversion:
                    raise ValueError("length templates only support the plain {chars} variable")
                variables.append(name)
        if not variables:
            raise ValueError("length templates must retain {chars}")
    return value.replace("\r\n", "\n").replace("\r", "\n")


def effective_template(values, field):
    return checked_template(field, values.get(field, PROMPT_DEFAULTS[field]))

"""Sərbəst mətn analitikası — ümumi təkliflər və açar söz tezliyi (xarici NLP YOXDUR).

ANONİMLİK:
* Ümumi bölmənin təklifləri KAMPANİYA BAŞINA k-həddi ilə açılır: dəstdə bir neçə
  kampaniya birləşəndə hər kampaniyanın öz ``min_group_size``-ı (≥ 3) yoxlanır və
  daraldıcı filtrdə tamamlayıcı qayda da tətbiq olunur — k-dan az cavablı
  kampaniyanın mətni heç vaxt qaytarılmır (``hidden_campaigns`` yalnız SAYDIR).
* Mətnlər identifikatorsuz, təsadüfi UUID sırası ilə qaytarılır — kampaniya, fənn,
  qrup, tarix və ya sual id-si ilə birlikdə YOX.
* Açar söz tezliyi SƏNƏD tezliyidir (söz neçə təklifdə keçir) və ən azı 2 təklifdə
  keçən sözlər göstərilir — tək bir cavabın xarakterik ifadəsi ayrıca üzə çıxmır.
"""

from __future__ import annotations

import re
from collections import Counter

from django.db.models import Count

from ..constants import DEFAULT_MIN_GROUP_SIZE, QuestionKind, Section
from ..models import SurveyAnswer, SurveyCampaign
from . import filters as flt
from .analytics import is_visible

#: Ekranda göstərilən təklif sayının tavanı (qalanı axtarışla daraldılır).
SUGGESTION_LIMIT = 200
#: Açar söz analizinə daxil edilən mətn sayının tavanı (yaddaş/CPU sərhədi).
KEYWORD_CAP = 3000
#: Açar söz siyahısının uzunluğu və minimum sənəd tezliyi.
KEYWORD_TOP = 30
KEYWORD_MIN_DOCS = 2

#: Azərbaycan dilinin köməkçi sözləri + tez-tez işlənən ümumi fellər (analizdən çıxarılır);
#: tələbələr bəzən rus/ingilis dilində yazır — onların ən ümumi sözləri də əlavə olunub.
STOPWORDS_AZ = frozenset("""
    və ilə üçün da də ki bu o bir iki çox daha amma lakin ancaq həm hər nə niyə necə kimi
    olan olsun olur olub olar oldu olmaq olmalı olmalıdır olmasın olmur olsa olunsun olunur
    edir edirlər edək etmək etsin etsinlər edilsin edilməlidir edilir edərdim edirəm elə
    eləmək etməli etməlidir etməyi var yox yoxdur yoxdu deyil deyildi mən sən biz siz onlar
    bizim sizin onların onun mənim sənin bizə sizə bizi sizi öz özü özləri belə isə ya yaxud
    əgər çünki ona buna bunu onu bunun hansı harada burada orada artıq hələ yenə ən qədər
    sonra əvvəl indi bütün bəzi heç həmişə bəzən az lazım lazımdır istəyirəm istərdim
    fikrim fikrimcə məncə hamısı hamı şey şeylər tərəfindən görə başqa digər eyni kim kimə
    nəyi üzrə qarşı arasında içində barədə haqqında zaman vaxt gərək gərəkdir daim tam
    yalnız sadəcə hətta həmçinin habelə yəni əsasən xüsusilə mümkün mümkünsə olaraq
    təklif təklifim təklifimiz edərdik
    the and for are but not you with this that have from they was were will would should
    could there their what which about more also very just can all any our your its
    это что как для все так его она они мне был было быть или если уже нет еще при
    """.split())

#: Söz (defisli birləşmə daxil: «wi-fi», «e-poçt»), ən azı 3 hərf.
_TOKEN_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)
_MIN_TOKEN = 3
#: YÜNGÜL şəkilçi kəsimi (NLP deyil): cəm, yerlik, çıxışlıq, yiyəlik — «kitabxanada»,
#: «kitabxanadan» və «kitabxana» bir söz sayılsın. Kök ən azı 5 hərf qalmalıdır
#: (qısa sözlər kəsilmir), uzun şəkilçi əvvəl yoxlanılır.
_SUFFIXES = (
    "larının",
    "lərinin",
    "ların",
    "lərin",
    "ları",
    "ləri",
    "dakı",
    "dəki",
    "lar",
    "lər",
    "dan",
    "dən",
    "tan",
    "tən",
    "nın",
    "nin",
    "nun",
    "nün",
    "da",
    "də",
    "ta",
    "tə",
)
_MIN_STEM = 5


def normalize(text) -> str:
    """Azərbaycan registr qaydası: «İ» → «i», «I» → «ı» (Python ``lower`` bunu bilmir)."""
    return str(text or "").replace("İ", "i").replace("I", "ı").lower()


def stem(word) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM:
            return word[: -len(suffix)]
    return word


def keywords_of(text) -> dict:
    """``{kök: səth forması}`` — mətndəki analizə daxil sözlər (stop-sözlər çıxılıb)."""
    found = {}
    for word in _TOKEN_RE.findall(normalize(text)):
        if len(word) < _MIN_TOKEN or word in STOPWORDS_AZ:
            continue
        root = stem(word)
        if root not in STOPWORDS_AZ:
            found.setdefault(root, word)
    return found


def keyword_frequency(texts, *, top=KEYWORD_TOP, min_docs=KEYWORD_MIN_DOCS) -> list:
    """``[{"word", "stem", "count"}]`` — söz (kök) neçə mətndə keçir (sənəd tezliyi),
    azalan sıra. ``word`` — kök özü mətndə işlənibsə kök, əks halda ən çox işlənən forma;
    axtarış ``stem`` ilə aparılır (bütün şəkilçili formaları tutur)."""
    counter: Counter = Counter()
    surfaces: dict = {}
    for text in texts:
        for root, word in keywords_of(text).items():
            counter[root] += 1
            surfaces.setdefault(root, Counter())[word] += 1
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    result = []
    for root, count in ranked:
        if count < min_docs:
            continue
        forms = surfaces[root]
        result.append({"word": root if root in forms else forms.most_common(1)[0][0], "stem": root, "count": count})
        if len(result) >= top:
            break
    return result


def _visible_campaigns(organization, scope, filters, campaign_ids):
    base = flt.responses(organization, scope, filters, campaign_ids, section=Section.GENERAL)
    counts = dict(base.values("campaign_id").annotate(c=Count("id")).values_list("campaign_id", "c"))
    wide = {}
    if filters.is_narrowed and counts:
        wide = dict(
            flt.responses(organization, scope, filters.without_narrowing(), campaign_ids, section=Section.GENERAL)
            .values("campaign_id")
            .annotate(c=Count("id"))
            .values_list("campaign_id", "c")
        )
    thresholds = dict(
        SurveyCampaign.objects.filter(pk__in=list(counts)).values_list("pk", "min_group_size") if counts else []
    )
    visible = []
    for campaign_id, count in counts.items():
        k = max(int(thresholds.get(campaign_id) or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE)
        if is_visible(count, k, wide.get(campaign_id) if filters.is_narrowed else None):
            visible.append(campaign_id)
    return base, counts, visible


def suggestion_digest(organization, scope, filters=None, *, query="", limit=SUGGESTION_LIMIT) -> dict:
    """``{"k", "n", "visible_n", "suppressed", "hidden_campaigns", "total", "truncated",
    "items": [mətn, …], "keywords": [{"word", "count"}]}`` — ümumi bölmənin təklifləri."""
    filters = filters or flt.ResultFilters()
    campaign_ids = flt.campaign_ids_for(organization, filters)
    result = {
        "k": 0,
        "n": 0,
        "visible_n": 0,
        "suppressed": True,
        "hidden_campaigns": 0,
        "total": 0,
        "truncated": False,
        "items": [],
        "keywords": [],
    }
    if not campaign_ids or not scope.has_structure_access:
        return result
    base, counts, visible = _visible_campaigns(organization, scope, filters, campaign_ids)
    result.update(
        k=flt.k_threshold(campaign_ids),
        n=sum(counts.values()),
        visible_n=sum(counts[campaign_id] for campaign_id in visible),
        hidden_campaigns=len(counts) - len(visible),
        suppressed=not visible,
    )
    if not visible:
        return result
    answers = SurveyAnswer.objects.filter(
        response__in=base.filter(campaign_id__in=visible).values("pk"), question__kind=QuestionKind.TEXT
    ).exclude(text="")
    for pattern in flt.text_regex(query or filters.text_query):
        answers = answers.filter(text__iregex=pattern)
    texts = list(answers.order_by("pk").values_list("text", flat=True)[: KEYWORD_CAP + 1])
    truncated = len(texts) > KEYWORD_CAP
    texts = texts[:KEYWORD_CAP]
    result.update(
        total=len(texts),
        truncated=truncated,
        items=texts[: max(0, int(limit))],
        keywords=keyword_frequency(texts),
    )
    return result

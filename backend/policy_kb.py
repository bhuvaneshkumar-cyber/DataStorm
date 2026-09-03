"""Credit-policy knowledge base and the retrieval behind the in-app bot.

Deliberately not a language model. The questions this answers are about *our*
published policy -- what the sweep threshold is, when a loan is declined, how
long a statement is kept -- and those have exactly one correct answer that must
not drift between sessions or get invented on a bad day. A keyword retriever
over a curated base is auditable, runs with no API key, costs nothing, and
cannot hallucinate a covenant that does not exist.

ponytail: token-overlap retrieval, no embeddings. Swap in a vector index if the
base outgrows a page of entries and near-synonyms start missing.

Every answer exists in each supported language rather than being translated on
the fly, so an answer about interest rates cannot be reworded into something
that is no longer true.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List

DEFAULT_LANGUAGE = "en"

# Words that appear in almost every question and would otherwise let a long
# question match everything equally.
_STOPWORDS = frozenset(
    """a an and are as at be by can could do does for from get has have how i if in is it
    me my of on or should so tell that the their there they this to was what when where
    which who why will with would you your""".split()
)

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)

# A keyword hit is worth more than an incidental word in the answer body.
_KEYWORD_WEIGHT = 3.0
_BODY_WEIGHT = 1.0

# Below this, the retriever says it does not know instead of returning its least
# bad guess. Tuned so a genuine off-topic question ("what is the weather") falls
# through while a clumsily worded on-topic one still lands.
_CONFIDENCE_THRESHOLD = 1.2


def normalize(text: str) -> List[str]:
    """Lowercased, accent-folded, stopword-free tokens.

    NFKD folding matters for the Indic languages: the same word typed with a
    composed or decomposed vowel sign must produce the same token.
    """
    folded = unicodedata.normalize("NFKD", text.casefold())
    return [t for t in _TOKEN_RE.findall(folded) if t not in _STOPWORDS and len(t) > 1]


@dataclass(frozen=True)
class PolicyEntry:
    """One published policy, its answer per language, and how to find it."""

    topic: str
    keywords: tuple[str, ...]
    answers: Dict[str, str]
    _keyword_tokens: frozenset = field(default=frozenset(), repr=False, compare=False)

    def answer_in(self, language: str) -> str:
        return self.answers.get(language) or self.answers[DEFAULT_LANGUAGE]


def _entry(topic: str, keywords: str, en: str, hi: str, ta: str) -> PolicyEntry:
    kw = tuple(keywords.split())
    return PolicyEntry(
        topic=topic,
        keywords=kw,
        answers={"en": en, "hi": hi, "ta": ta},
        _keyword_tokens=frozenset(normalize(" ".join(kw))),
    )


# --------------------------------------------------------------------------- #
# The base. Every number here must match the code that enforces it:
# savings.py for sweeps, ml_service/config.py for bands and pricing.
# --------------------------------------------------------------------------- #

POLICY_BASE: tuple[PolicyEntry, ...] = (
    _entry(
        "How the credit score works",
        "credit score alternative cibil bureau calculated hybrid rules model points 800",
        "Your score runs from 0 to 800 and is built without a CIBIL or bureau record. "
        "Forty percent comes from transparent rules on your savings buffer, income "
        "stability, platform rating and workload; sixty percent comes from a model "
        "trained on the same signals. If the model is unavailable the score falls back "
        "to rules alone and is labelled as such.",
        "Aapka score 0 se 800 tak hota hai aur ise CIBIL ya kisi bureau record ke bina "
        "banaya jaata hai. Chalis pratishat aapke savings buffer, income sthirta, "
        "platform rating aur kaam ke ghanton par aadharit spasht niyamon se aata hai; "
        "saath pratishat ek model se. Model uplabdh na ho to score keval niyamon par "
        "banta hai aur aisa hi darshaya jaata hai.",
        "Ungal matippen 0 mudhal 800 varai; CIBIL allathu bureau pathivu illaamalye "
        "kanakkidappadugirathu. Naarpathu sathaveetham ungal semippu, varumana "
        "nilaithanmai, platform mathippeedu, velai neram aagiyavatrin thelivaana "
        "vidhigalil irundhu varugirathu; arupathu sathaveetham oru modelil irundhu. "
        "Model kidaikkaavittal matippen vidhigalai mattum kondu kanakkidappadum.",
    ),
    _entry(
        "Score bands and what they mean",
        "band category good standard poor excellent grade gs approve refer decline threshold",
        "Six hundred and above is Good, four hundred to six hundred is Standard, and "
        "below four hundred is Poor. Six eighty and above prices as the lowest risk "
        "tier. The same boundaries drive the decision, so a Good applicant can never "
        "come back declined.",
        "Chhah sau ya usse adhik Good hai, chaar sau se chhah sau Standard hai, aur "
        "chaar sau se kam Poor hai. Chhah sau assi ya adhik par sabse kam risk ki "
        "keemat lagti hai. Yahi seemayein nirnay bhi tay karti hain, isliye Good "
        "aavedak kabhi asweekrit nahin ho sakta.",
        "Arunooru allathu athigam endral Good, nannooru mudhal arunooru varai "
        "Standard, nannooruku keezh Poor. Arunootru embathukku mel mikavum kuraindha "
        "aabathu nilai. Ithe ellaigale mudivaiyum thirmaanikkindrana, enave Good "
        "endru matippidappattavar oruporhtum nirakarikkappada maattaar.",
    ),
    _entry(
        "Emergency loan eligibility",
        "loan emergency borrow apply eligible eligibility qualify limit amount tenor",
        "You can apply for an emergency loan once your alternative credit score "
        "reaches four hundred. Below that the application is not accepted at all "
        "rather than being taken and declined. Your ceiling is a multiple of your "
        "monthly platform income -- three times at the lowest risk tier, two times at "
        "moderate, one time at high -- and the tenor runs from six to twenty-four "
        "months on the same scale.",
        "Jab aapka alternative credit score chaar sau tak pahunchta hai tab aap "
        "emergency loan ke liye aavedan kar sakte hain. Usse kam par aavedan liya hi "
        "nahin jaata. Aapki seema aapki maasik platform aay ka gunak hai -- sabse kam "
        "risk par teen guna, madhyam par do guna, uchch par ek guna -- aur avadhi "
        "chhah se chaubis maheene tak hoti hai.",
        "Ungal maatru kadan matippen nannooru adaindha pinnar avasara kadanukku "
        "vinnappikkalaam. Athatku keezh vinnappame etrukkollappaduvathillai. Ungal "
        "uchcha varambu ungal maatha platform varumaanathin madangu -- kuraindha "
        "aabathil moondru madangu, nadutharathil irandu, uyarvil ondru -- kaalam aaru "
        "mudhal irubathi naangu maadhangal.",
    ),
    _entry(
        "How a lender decides",
        "lender decision approve reject rejected approval reviewed portal underwriting",
        "A lender sees your score, its risk grade, the indicative rate, your requested "
        "amount and tenor, and the early warning signals behind the number -- never "
        "your raw statement or your transaction list. They approve or reject with a "
        "note. The score attached to an application is frozen at the moment you "
        "applied, so a later change cannot rewrite the basis of a decision.",
        "Rinadata aapka score, uska risk grade, sanketik dar, aapki maangi gayi rashi "
        "aur avadhi, aur us sankhya ke peechhe ke chetavani sanket dekhta hai -- aapka "
        "statement ya lenden ki soochi kabhi nahin. Ve tippani ke saath sweekar ya "
        "asweekar karte hain. Aavedan se juda score aavedan ke samay hi sthir ho jaata hai.",
        "Kadan valangubavar ungal matippen, athan aabathu tharam, kurippitta vatti "
        "veedham, neengal ketta thogai matrum kaalam, matrum eccharikkai kurippugalai "
        "mattume paarkiraar -- ungal statement allathu paribavarthanai pattiyalai "
        "alla. Avargal kurippudan ottukolvar allathu nirakarippar. Vinnappathudan "
        "inaikkappatta matippen vinnappitha nerathil nilaiyaaga uraiyum.",
    ),
    _entry(
        "Round-up sweeps and the mandate cap",
        "sweep roundup round up autopay upi mandate threshold hundred stash savings automatic",
        "A spend is rounded up to the next fifty rupees and the difference is held as "
        "a pending contribution. Nothing moves until pending contributions reach one "
        "hundred rupees, and no single sweep may exceed your UPI AutoPay mandate cap "
        "of one thousand rupees. Both limits are yours to change.",
        "Har kharch ko agle pachaas rupaye tak poora kiya jaata hai aur antar lambit "
        "yogdan ke roop mein rakha jaata hai. Jab tak lambit yogdan sau rupaye nahin "
        "pahunchta tab tak kuch nahin hilta, aur koi bhi ek sweep aapki UPI AutoPay "
        "seema ek hazaar rupaye se adhik nahin ho sakta. Dono seemayein aap badal sakte hain.",
        "Ovvoru selavum adutha aimbathu roobaikku muzhumaipadutthappattu vithiyaasam "
        "nilubaiyil vaikkappadum. Nilubai nooru roobaiyai adaiyum varai edhuvum "
        "nagarathu, matrum oru sweep ungal UPI AutoPay varambu aayiram roobaiyai "
        "thaanda mudiyaathu. Irandu varambugalaiyum neengal maatralaam.",
    ),
    _entry(
        "Income smoothing surplus",
        "surplus smoothing payout average thirty day rolling income baseline extra",
        "When a payout lands above your rolling thirty-day average, ten percent of the "
        "excess is set aside on top of your round-ups. A payout at or below the "
        "average contributes nothing, so a lean week never draws money out of your hands.",
        "Jab koi payout aapke tees din ke chalte ausat se adhik hota hai, tab adhik "
        "rashi ka das pratishat aapke round-up ke upar alag rakha jaata hai. Ausat ke "
        "baraabar ya kam payout se kuch nahin jaata, isliye kamzor hafte mein aapke "
        "haath se paisa nahin nikalta.",
        "Oru payout ungal muppathu naal sarasariyai vida athigamaaga irundhaal, "
        "athiga thogaiyin pathu sathaveetham ungal round-up mel serkkappadum. "
        "Sarasariyai vida kuraivaana payout edhaiyum thara vendaam, enave kadinamaana "
        "vaarathil ungal kaiyilirundhu panam pogaathu.",
    ),
    _entry(
        "Withdrawing from the Resilience Stash",
        "withdraw withdrawal money back lean week access stash locked penalty",
        "The Resilience Stash is yours and is not locked. A withdrawal returns to your "
        "primary bank account with no penalty and no notice period. Withdrawing does "
        "lower your savings buffer, which is the single strongest input to your score, "
        "so the score will move.",
        "Resilience Stash aapka hai aur band nahin hai. Nikaasi bina kisi jurmaane aur "
        "bina soochna avadhi ke aapke mukhya bank khaate mein wapas jaati hai. Nikaalne "
        "se aapka savings buffer ghatta hai, jo aapke score ka sabse majboot aadhaar "
        "hai, isliye score badlega.",
        "Resilience Stash ungaludaiyathu, athu poottappadavillai. Edukkum thogai "
        "arupanam illaamal ungal mukkiya vangi kanakkukku thirumbum. Aanal semippu "
        "kuraivathaal ungal matippen -- athan mikka valuvaana kooru -- maarum.",
    ),
    _entry(
        "What a statement upload is used for",
        "statement upload document pdf csv excel privacy stored deleted retention data",
        "An uploaded statement is parsed in memory, scored, and the temporary file is "
        "deleted before the response is returned. Nothing from the document is stored. "
        "The response shows which figures were read from the statement, which you "
        "supplied, and which fell back to a documented default.",
        "Upload kiya gaya statement memory mein padha jaata hai, score kiya jaata hai, "
        "aur uttar lautne se pehle asthaayi file mita di jaati hai. Dastavez se kuch "
        "bhi sanchit nahin hota. Uttar dikhata hai kaun se aankde statement se aaye, "
        "kaun se aapne diye, aur kaun se default se.",
        "Pathivetrappatta statement ninaivagathil aayvu seyyappattu, matippidappattu, "
        "badhil thirumbum munbe thatkaalika file azhikkappadum. Aavanathil irundhu "
        "edhuvum sekarikkappaduvathillai. Enda enngal statementil irundhu vandhana, "
        "enna neengal alitheergal endru badhil kaattum.",
    ),
    _entry(
        "Which documents can be read",
        "format pdf csv excel word docx scanned ocr image supported file size",
        "PDF, CSV, Excel, Word and plain text are supported, up to twenty-five "
        "megabytes. Bordered and borderless PDF tables are both handled, and a scanned "
        "PDF falls back to OCR. Indian formatting is read natively: lakh and crore "
        "scale words, one-two-three digit grouping, bracketed negatives, and Cr meaning "
        "credit rather than crore.",
        "PDF, CSV, Excel, Word aur saadaa text sweekar hain, pachchis megabyte tak. "
        "Border wali aur bina border wali dono PDF tables padhi jaati hain, aur scan "
        "ki gayi PDF ke liye OCR ka upyog hota hai. Bhaartiya format seedhe padha jaata "
        "hai: laakh aur karod, ank samuhan, kosthak mein rinatmak, aur Cr ka arth credit.",
        "PDF, CSV, Excel, Word matrum elimaiyaana text -- irubathi aindhu megabyte "
        "varai. Elai ulla matrum elai illaadha PDF attavanaigal irandume "
        "kaiyaalappadugindrana; scan seyyappatta PDF-ku OCR payanpadum. Indhiya "
        "vadivam nerdiyaaga padikkappadum: laksham, kodi, adaipputkuriyil ethirmarai.",
    ),
    _entry(
        "Micro insurance recommendation",
        "insurance cover policy premium micro health accident recommend protection",
        "Insurance advice is generated from your risk score and employment type, not "
        "sold. It ranks accident, health, income-protection and asset cover by what "
        "your situation actually exposes you to, with an indicative monthly premium "
        "band for each. Nothing is bound and no premium is collected in this app.",
        "Bima salaah aapke risk score aur rozgaar prakaar se banti hai, bechi nahin "
        "jaati. Yah durghatna, swasthya, aay-suraksha aur sampatti cover ko aapki "
        "sthiti ke anusaar kram deti hai, pratyek ke liye sanketik maasik premium ke "
        "saath. Is app mein koi policy jaari nahin hoti aur premium nahin liya jaata.",
        "Kaappeedu aalosanai ungal aabathu matippen matrum velaivaaipu vagaiyil "
        "irundhu uruvaakkappadugirathu, virkappaduvathillai. Vibathu, sugaadhaaram, "
        "varumaana paathukaappu matrum sotthu kaappeedugalai varisaipadutthum. Indha "
        "seyliyil endha policy-yum valangappadavillai, premium-um vasoolikkappadavillai.",
    ),
    _entry(
        "Tax estimate basis",
        "tax income advance gst slab regime presumptive 44ad liability estimate filing",
        "The tax figure is an estimate from the income you have logged, annualised "
        "across the days observed. It assumes a resident individual under sixty on the "
        "default new regime, with presumptive taxation under section 44AD treating six "
        "percent of digital turnover as profit. It is not a filing and not tax advice.",
        "Kar ka aankda aapki darj ki gayi aay se anumaan hai, dekhe gaye dinon par "
        "vaarshik kiya gaya. Yah maanta hai ki aap saath varsh se kam ke nivaasi "
        "vyakti hain, nayi kar vyavastha par, aur dhaara 44AD ke tahat digital turnover "
        "ka chhah pratishat laabh maana jaata hai. Yah filing ya kar salaah nahin hai.",
        "Vari thogai neengal pathivu seydha varumaanathin adippadaiyil oru mathippeedu "
        "mattume, kavanikkappatta naatkalil irundhu aandukku maatrappattathu. Arupathu "
        "vayathukku keezhpatta kudiyirupbaalar, pudhiya vari muraiyil, pirivu 44AD-in "
        "keezh digital turnover-in aaru sathaveetham laabam ena karuthappadugirathu.",
    ),
    _entry(
        "Connecting a platform account",
        "platform connect link account swiggy uber zomato ola freelance proof verified",
        "Connecting a platform records the earnings, rating and hours it reports, and "
        "those become the evidence your score is built on. An account starts "
        "unverified and is marked verified once a payout you have logged corroborates "
        "it. You can disconnect at any time; the score then recomputes without it.",
        "Platform jodne par uski batayi gayi aay, rating aur ghante darj hote hain, aur "
        "wahi aapke score ka aadhaar bante hain. Khaata pehle asatyaapit hota hai aur "
        "tab satyaapit hota hai jab aapka darj kiya payout uski pushti karta hai. Aap "
        "kabhi bhi hata sakte hain; score bina uske dobara banta hai.",
        "Oru platform-ai inaikkumpothu athu therivikkum varumaanam, mathippeedu matrum "
        "nerangal pathivaagum -- ithuve ungal matippenin saandru. Kanakku "
        "saanraaikkappadaathathaaga thodangi, neengal pathivu seydha payout athai "
        "urudhipadutthum pothu saanraaikkappadum. Eppothu vendumaanaalum neekkalaam.",
    ),
)

# Offered when nothing matches, so a dead end still points somewhere useful.
_FALLBACK = {
    "en": "I only answer questions about this product's published financial policy -- "
    "scores, sweeps, loans, insurance, tax and how your documents are handled. "
    "Try one of these:",
    "hi": "Main keval is product ki prakashit vittiya niti se jude prashn ka uttar "
    "deta hoon -- score, sweep, loan, bima, kar aur aapke dastavezon ka upyog. "
    "Inmein se koi aazmaayein:",
    "ta": "Naan indha thayarippin veliyidappatta nithi kolgai patriya kelvigalukku "
    "mattume badhil alikkiren -- matippen, sweep, kadan, kaappeedu, vari matrum "
    "aavanangal. Ivatril ondrai muyarchi seyyungal:",
}


def _score_entry(entry: PolicyEntry, tokens: List[str]) -> float:
    """Weighted overlap, damped by question length.

    The square root is the point: dividing by the raw token count punishes a
    politely phrased question ("how much do I need before a sweep happens")
    until it scores below a terse one, while not dividing at all lets a long
    off-topic question accumulate a passing score from incidental hits.
    """
    if not tokens:
        return 0.0
    body = frozenset(normalize(entry.answers[DEFAULT_LANGUAGE] + " " + entry.topic))
    total = 0.0
    for token in tokens:
        if token in entry._keyword_tokens:
            total += _KEYWORD_WEIGHT
        elif token in body:
            total += _BODY_WEIGHT
    return round(total / len(tokens) ** 0.5, 3)


def answer(question: str, language: str = DEFAULT_LANGUAGE) -> dict:
    """Best policy answer for a question, or an honest 'I don't know'."""
    tokens = normalize(question)
    ranked = sorted(
        ((_score_entry(entry, tokens), entry) for entry in POLICY_BASE),
        key=lambda pair: pair[0],
        reverse=True,
    )

    best_score, best_entry = ranked[0]
    if best_score < _CONFIDENCE_THRESHOLD:
        return {
            "answer": _FALLBACK.get(language, _FALLBACK[DEFAULT_LANGUAGE]),
            "confident": False,
            "sources": [],
            "suggestions": [entry.topic for entry in POLICY_BASE[:4]],
        }

    return {
        "answer": best_entry.answer_in(language),
        "confident": True,
        "sources": [
            {"topic": entry.topic, "score": score} for score, entry in ranked[:3] if score > 0
        ],
        # Neighbours, so a near-miss is one tap from the right answer.
        "suggestions": [entry.topic for _, entry in ranked[1:4]],
    }


def topics() -> List[str]:
    """Everything the bot can answer, for the UI to offer up front."""
    return [entry.topic for entry in POLICY_BASE]


def demo() -> None:
    """Self-check: the retriever must route, and must decline to guess."""
    assert normalize("What IS the Sweep threshold?") == ["sweep", "threshold"]

    routed = {
        "how much do I need before a sweep happens": "Round-up sweeps and the mandate cap",
        "can I get an emergency loan": "Emergency loan eligibility",
        "do you keep my uploaded pdf statement": "What a statement upload is used for",
        "how is advance tax calculated": "Tax estimate basis",
        "why was my application rejected by the lender": "How a lender decides",
        "which insurance cover should I take": "Micro insurance recommendation",
    }
    for question, expected in routed.items():
        result = answer(question)
        assert result["confident"], f"expected a confident answer for {question!r}"
        assert result["sources"][0]["topic"] == expected, (
            f"{question!r} routed to {result['sources'][0]['topic']!r}, expected {expected!r}"
        )

    off_topic = answer("what is the weather in Chennai tomorrow")
    assert not off_topic["confident"]
    assert off_topic["suggestions"], "a fallback must still offer somewhere to go"

    # Every entry answers in every supported language, and none silently reuses
    # the English string as a stand-in for a translation.
    for entry in POLICY_BASE:
        for language in ("en", "hi", "ta"):
            assert entry.answers.get(language), f"{entry.topic} is missing {language}"
        assert entry.answers["hi"] != entry.answers["en"]
        assert entry.answers["ta"] != entry.answers["en"]

    hindi = answer("emergency loan", language="hi")
    assert hindi["answer"] != answer("emergency loan", language="en")["answer"]

    print(f"policy_kb.py self-check passed ({len(POLICY_BASE)} topics)")


if __name__ == "__main__":
    demo()

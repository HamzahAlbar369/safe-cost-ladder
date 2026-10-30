"""Phase 0 smoke-test PROBE fixtures. FICTIONAL. Not evaluation data.

Approved by Hamzah 2026-10-30 for Phase 0 only. These items and this draft policy text must NEVER be reused
in Phase 1 data generation or in any evaluation split. The real policy document is rendered from
data/rules/rules.yaml in Phase 1; this draft only gives the smoke test a realistic static prefix.
"""

from __future__ import annotations

from dataclasses import dataclass

FICTION_LABEL = (
    "FICTIONAL PROBE: Oasis Motor Insurance (fictional demo insurer). Not real Najm/SAMA/insurer rules."
)

DRAFT_POLICY_EN = """\
OASIS MOTOR INSURANCE (FICTIONAL DEMO INSURER) - DRAFT PROBE POLICY (Phase 0 smoke test only)
This document is fictional. It does not describe any real insurer, regulator or traffic authority.

1. Coverage types (R1)
1.1 TPL (third-party liability) covers damage the policyholder causes to other people's vehicles and
    property. It never covers the policyholder's own vehicle.
1.2 COMP (comprehensive) covers the policyholder's own vehicle and third-party damage.

2. Fault share (R2)
2.1 Fault is assigned in steps of 0, 25, 50, 75 or 100 percent, as written on the accident report.

3. Own-damage claims (R3, COMP only)
3.1 Payout = min(assessed damage, own-damage limit) minus the deductible.
3.2 Own-damage limit: 60,000 SAR per accident. Standard deductible: 1,000 SAR.
3.3 When the policyholder's fault share is 75% or more, the deductible doubles to 2,000 SAR.
3.4 A payout is never negative; if the deductible exceeds the damage, the payout is 0 and the claim is
    denied with reason R3.

4. Third-party claims against the policyholder (R4)
4.1 Payout = assessed third-party damage x policyholder fault share, capped at the TPL limit.
4.2 TPL limit: 100,000 SAR per accident.

5. Exclusions (R5) - the claim is denied when any of these hold:
5.1 The driver had no valid driving licence at the time of the accident.
5.2 The policy had expired on the accident date.
5.3 The vehicle was used commercially (e.g. paid ride-hailing or deliveries) under a private policy.

6. Reporting window (R6)
6.1 Claims must be reported within 30 days of the accident.
6.2 Claims reported later are denied unless the customer states a valid justification
    (hospitalisation, travel outside the Kingdom, or a documented official delay).

7. Required documents (R7)
7.1 Every claim needs an accident report number AND a damage estimate.
7.2 If either is missing, the decision is need_info; no payout is computed.

8. Frequently asked questions
8.1 How many days do I have to report a claim? 30.
8.2 What is the standard deductible? 1,000 SAR.
8.3 What is the deductible if I am 75% or more at fault? 2,000 SAR.
8.4 Does TPL cover my own car? No.
8.5 What is the own-damage limit? 60,000 SAR.
8.6 What is the third-party limit? 100,000 SAR.
8.7 Are rideshare trips covered under a private policy? No.
8.8 Which documents are required? Accident report number and damage estimate.
"""

DRAFT_POLICY_AR = """\
واحة للتأمين على المركبات (شركة تأمين خيالية لأغراض العرض) - مسودة وثيقة اختبار (لاختبار المرحلة صفر فقط)
هذه الوثيقة خيالية ولا تمثل أي شركة تأمين أو جهة تنظيمية أو مرورية حقيقية.

1. أنواع التغطية (R1)
1.1 تأمين ضد الغير (TPL) يغطي الأضرار التي يسببها حامل الوثيقة لمركبات الآخرين وممتلكاتهم، ولا يغطي مركبة حامل الوثيقة.
1.2 التأمين الشامل (COMP) يغطي مركبة حامل الوثيقة وأضرار الغير.

2. نسبة الخطأ (R2)
2.1 تُحدد نسبة الخطأ بإحدى القيم: 0 أو 25 أو 50 أو 75 أو 100 بالمئة كما وردت في تقرير الحادث.

3. مطالبات أضرار المركبة الذاتية (R3، للتأمين الشامل فقط)
3.1 التعويض = أقل قيمة بين الضرر المقدّر وحد الأضرار الذاتية، مطروحاً منه مبلغ التحمل.
3.2 حد الأضرار الذاتية: 60,000 ريال لكل حادث. مبلغ التحمل القياسي: 1,000 ريال.
3.3 إذا كانت نسبة خطأ حامل الوثيقة 75% أو أكثر يتضاعف مبلغ التحمل إلى 2,000 ريال.
3.4 لا يكون التعويض سالباً أبداً؛ إذا زاد مبلغ التحمل عن الضرر يكون التعويض صفراً وتُرفض المطالبة بالسبب R3.

4. مطالبات الغير ضد حامل الوثيقة (R4)
4.1 التعويض = ضرر الغير المقدّر × نسبة خطأ حامل الوثيقة، بحد أقصى حد التأمين ضد الغير.
4.2 حد التأمين ضد الغير: 100,000 ريال لكل حادث.

5. الاستثناءات (R5) - تُرفض المطالبة في أي من الحالات التالية:
5.1 لم يكن لدى السائق رخصة قيادة سارية وقت الحادث.
5.2 كانت الوثيقة منتهية في تاريخ الحادث.
5.3 استُخدمت المركبة استخداماً تجارياً (مثل التوصيل أو نقل الركاب بأجر) بموجب وثيقة خاصة.

6. مهلة الإبلاغ (R6)
6.1 يجب الإبلاغ عن المطالبة خلال 30 يوماً من تاريخ الحادث.
6.2 تُرفض المطالبات المبلغ عنها بعد ذلك ما لم يذكر العميل عذراً مقبولاً (التنويم في المستشفى، أو السفر خارج المملكة، أو تأخير رسمي موثق).

7. المستندات المطلوبة (R7)
7.1 تتطلب كل مطالبة رقم تقرير الحادث وتقدير الأضرار معاً.
7.2 إذا نقص أي منهما يكون القرار need_info ولا يُحسب أي تعويض.
"""

TASK_INSTRUCTIONS = """\
You are the claims-desk assistant for Oasis Motor Insurance (a fictional demo insurer). Answer ONLY from
the policy document below. Tickets may be in English or Arabic (MSA or Saudi dialect); always answer in the
JSON format for the task. Output exactly one JSON object and nothing else: no prose, no markdown fences.
Normalise numbers to ASCII digits without thousands separators; dates to ISO YYYY-MM-DD.

Each user message starts with "TASK: <task>" followed by the ticket text.

TASK faq - a customer question about the policy.
  Output: {"answer": <number | "yes" | "no" | short canonical string>}

TASK intent - classify a free-text ticket into exactly one label:
  new_claim, claim_status, coverage_question, document_submission, complaint, policy_change,
  payment_issue, other.
  Output: {"intent": "<label>"}

TASK extract - pull fields from a claim message; use null for any field that is absent.
  Output: {"policy_number": str|null, "accident_date": "YYYY-MM-DD"|null, "report_number": str|null,
           "damage_amount_sar": int|null, "fault_share": int|null}

TASK adjudicate - decide a claim under the policy rules.
  Output: {"decision": "approve"|"partial"|"deny"|"need_info", "payout_sar": int,
           "reasons": [rule ids such as "R3"], "inputs": {facts you used, e.g. coverage, fault_share,
           damage_sar, days_to_report, documents}}
  payout_sar is 0 for deny and need_info.
"""

STATIC_PREFIX = f"{TASK_INSTRUCTIONS}\n=== POLICY DOCUMENT (EN) ===\n{DRAFT_POLICY_EN}\n=== POLICY DOCUMENT (AR) ===\n{DRAFT_POLICY_AR}"

EXPECTED_KEYS: dict[str, set[str]] = {
    "faq": {"answer"},
    "intent": {"intent"},
    "extract": {"policy_number", "accident_date", "report_number", "damage_amount_sar", "fault_share"},
    "adjudicate": {"decision", "payout_sar", "reasons", "inputs"},
}


@dataclass(frozen=True)
class ProbeItem:
    id: str
    task: str
    matrix_language: str  # language used in the Anthropic matrix (check 1)
    en: str
    ar: str

    @property
    def text(self) -> str:
        return self.en if self.matrix_language == "en" else self.ar


PROBE_ITEMS: tuple[ProbeItem, ...] = (
    ProbeItem(
        id="probe-1-faq",
        task="faq",
        matrix_language="en",
        en="Hi, what deductible do I pay on my comprehensive policy if the report says I was 75% at fault?",
        ar="مرحباً، كم مبلغ التحمل في وثيقتي الشاملة إذا كان التقرير يقول إن نسبة خطئي 75%؟",
    ),
    ProbeItem(
        id="probe-2-intent",
        task="intent",
        matrix_language="ar",
        en="Hello, I filed a claim last week and I want to know what happened with it.",
        ar="السلام عليكم، رفعت مطالبة الأسبوع اللي فات وأبي أعرف وش صار عليها.",
    ),
    ProbeItem(
        id="probe-3-extract",
        task="extract",
        matrix_language="en",
        en=(
            "Policy OMI-4471-2209. Someone hit my car at a roundabout on 3 September 2026. The accident report "
            "number is AR-558120 and the garage estimate is 12,400 SAR. I was found 25% at fault."
        ),
        ar=(
            "الوثيقة OMI-4471-2209. صدمني شخص عند الدوار بتاريخ 3 سبتمبر 2026. رقم تقرير الحادث AR-558120 "
            "وتقدير الورشة 12,400 ريال. نسبة خطئي 25%."
        ),
    ),
    ProbeItem(
        id="probe-4-adjudicate",
        task="adjudicate",
        matrix_language="en",
        en=(
            "Comprehensive policy, valid until 2027-02-01. Accident on 2026-10-12, reported 2026-10-20. "
            "Driver holds a valid licence; private use. Accident report AR-771203 shows 50% fault. Garage "
            "damage estimate for my own car: 18,000 SAR. Please process my claim."
        ),
        ar=(
            "وثيقة شاملة سارية حتى 2027-02-01. الحادث بتاريخ 2026-10-12 وتم الإبلاغ في 2026-10-20. السائق "
            "يحمل رخصة سارية والاستخدام خاص. تقرير الحادث AR-771203 يبين نسبة خطأ 50%. تقدير الورشة "
            "لأضرار سيارتي: 18,000 ريال. أرجو معالجة مطالبتي."
        ),
    ),
    ProbeItem(
        id="probe-5-adjudicate",
        task="adjudicate",
        matrix_language="ar",
        en=(
            "I have comprehensive cover. Someone reversed into me in a mall car park on 2026-10-25 and I am "
            "reporting it today, 2026-10-27. The workshop estimated 6,500 SAR for my car. I don't have the "
            "accident report number yet. My licence is valid and the car is for personal use."
        ),
        ar=(
            "عندي تأمين شامل. واحد رجع بسيارته علي في مواقف المول يوم 2026-10-25 وأبلغ عنه اليوم 2026-10-27. "
            "الورشة قدرت الضرر على سيارتي بـ 6,500 ريال. ما عندي رقم تقرير الحادث للحين. رخصتي سارية والسيارة "
            "للاستخدام الشخصي."
        ),
    ),
)


def user_message(item: ProbeItem, language: str | None = None) -> str:
    """SPEC §6.2: user = task type + ticket text only."""
    text = item.text if language is None else (item.en if language == "en" else item.ar)
    return f"TASK: {item.task}\n{text}"


# Jev zero-shot router probe questions (ticket text only, no policy doc; SPEC §6.4).
# Phase 0 measures reachability, latency and EN/AR agreement only. The answer -> rung mapping is declared in
# DECISIONS.md before any router evaluation (Phase 2/3), not here.
JEV_QUESTIONS_SPEC: dict[str, dict] = {
    "complexity": {
        "kind": "choice",
        "instructions": "How much reasoning does answering this insurance customer ticket require?",
        "criteria": {
            "simple": "A single fact lookup or classifying what the customer wants.",
            "moderate": "Pulling several specific fields (numbers, dates, ids) out of the message.",
            "complex": "Deciding a claim by applying several policy rules and possibly computing a payout.",
        },
    },
    "needs_calculation": {
        "kind": "noul",
        "instructions": "Does answering this ticket require computing a monetary amount?",
    },
    "missing_information": {
        "kind": "noul",
        "instructions": "Is information the insurer needs to decide this ticket clearly missing?",
    },
}

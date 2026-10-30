# Review batch 1 — blind (no gold)

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

Write your answer for each item, then compare with `batch_1_gold.md`.

## dev-0370 · Arabic · intent

```text
ملاحظة مكالمة: اتصال من ريم على خط المطالبات.
أقود سيارة Hyundai Sonata 2020.
الوثيقة OMI-8997086.
إذا قاد أخي سيارتي ووقع حادث، فهل يشمله التأمين؟
```

My answer:

## dev-0161 · English · adjudicate

```text
Call note: customer Mohammed phoned the claims line.
- Policy: OMI-0612027
- Cover: third-party (TPL)
- Policy end: 24/02/2027
- Claim type: own damage
- Other party: identified, insured
- Accident date: 18/09/2026
- Report by: Najm
- Report no.: NJ-52998068
- Fault share: 75%
- Assessed repair cost: SAR 19,500
- Claim filed: 26/09/2026
- Customer says: On 18/09/2026 I was in a collision with another vehicle in Hail. I have attached the Najm accdient report, the istimara, the licence copy, the damage photos and the Taqdeer assessment. My phone number is 0574965210.
```

My answer:

## dev-0241 · English · faq

```text
Call note: customer Maha phoned the claims line.
I'm thinking about my cover before a trip to Tabuk.
What is the number of required documents for a claim, ya akhi?
```

My answer:

## dev-0290 · English · extract

```text
Call note: customer Majed phoned the claims line.
- Policy: OMI-8534970
- Cover: comprehensive
- Policy end: 22/02/2027
- Accident date: 5 Aug 2026
- Report by: Najm
- Report no.: NJ-51216883
- Assessed repair cost: SAR 10,800
- Claim filed: 6 Aug 2026
- Customer says: On 5 Aug 2026 I was in a collision with another vehicle in Jeddah. My phone number is 0577797027. The other driver was polite about the whole thing.
```

My answer:

## dev-0379 · Arabic · intent

```text
أود أن أشرح ما حدث.
الوثيقة OMI-1227387. اسمي تركي. أقود سيارة Lexus ES 2022. أشعر بساتياء شديد من تعامل موظفيكم معي في الفرع وأريد تسجيل شكوى.
ما الإجراء التالي؟
```

My answer:

## dev-0098 · English · adjudicate

```text
I need to tell you what happened.
My policy number is OMI-1704830 and I have comprehensive cover, valid until 10 February 2027. On 28 July 2026 someone hit my parked car in Buraidah and drove off. It was a hit-and-run. The accident was reported to the traffic police; the report number is TP-66480101. The Taqdeer assessment values the repairs to my car at 17,600 SAR. The sum insured on my schedule is 190,000 SAR. I am reporting this claim to you on 3 August 2026. Attached are the traffic police accident report, the istimara, the licence copy, the damage photos and the Taqdeer assessment.
What happens now?
```

My answer:

## dev-0345 · English · faq

```text
Here is my situation.
I'm a customer in Riyadh. I'm thinking about my cover before a trip to Riyadh. um, my name is Lama and I drive a Hyundai Sonata 2020. Is a rental car included in the base policy?
What happens now?
```

My answer:

## dev-0074 · English · adjudicate

```text
Dear Oasis claims team,
My policy number is OMI-8338863 and I have third-party (TPL) cover, valid until 14 February 2026. On 24 January 2026 I hit another car in Riyadh. The other driver, Yousef, is claiming against my policy. Najm attended and issued report NJ-58772029, which puts me at 50% fault. The damage assessment report for the other car comes to SAR 28,200. I'm filing the claim today, 28 January 2026. I have attached the Najm accident report, the other car's registration (istimara), the at-fault driver's licence copy, photos of the damage to the other car and the Taqdeer assessment of the other car.
Thank you,
Noura
```

My answer:

## dev-0106 · Arabic · adjudicate

```text
ملخص الموظف - مكالمة من عمر.
- الوثيقة: OMI-8918142
- التغطية: ضد الغير (TPL)
- انتهاء الوثيقة: 7 ديسمبر 2026
- نوع المطالبة: مطالبة طرف ثالث ضدي
- الطرف الآخر: معروف ومؤمَّن عليه
- تاريخ الحادث: 4 مارس 2026
- جهة التقرير: نجم
- رقم التقرير: NJ-99705473
- نسبة الخطأ: 0%
- أضرار الطرف الثالث (مقيّمة): 58,600 ريال سعودي
- تاريخ تقديم المطالبة: 11 مارس 2026
- إفادة العميل: في 4 مارس 2026 وقع لي حادث في الرياض، والطرف الآخر تركي يطالب بالتعويض من وثيقتي. كنت أنا من يقود وقت الحادث. أرفقتُ تقرير الحادث من نجم، رخصة سير مركبة الطرف الآخر (الاسمتارة)، نسخة من رخصة السائق المتسبب، صور تلفيات سيارة الطرف الآخر وتقرير تقدير (Taqdeer) لسيارة الطرف الآخر. الحمد لله لم يُصب أحد.
```

My answer:

## dev-0033 · Arabic · adjudicate

```text
السادة فريق المطالبات في واحة لتأمين المركبات المحترمين، السلام عليكم ورحمة الله وبركاته،
رقم وثيقتي OMI-4061969 ونوع التغطية تأمين شامل (COMP)، وهي سارية حتى 17 ديسمبر 2026. في 10 أغسطس 2026 وقع لي حادث في الرياض، والطرف الآخر هيا يطالب بالتعويض من وثيقتي. باشر نجم الحادث وأصدر التقرير رقم NJ-73917110، وحُمّلت فيه نسبة خطأ 25%. عمومًا، قدّمت الورشة عرض سعر للإصلاح بمبلغ 29,900 ريال، ولم يصدر تقرير تقييم الأضرار بعد. أتقدم بهذه المطالبة بتاريخ 15 أغسطس 2026. أرفقتُ تقرير الحادث من نجم، رخصة سير مركبة الطرف الآخر (الاستمارة)، نسخة من رخصة السائق المتسبب وصور تلفيات سيارة الطرف الآخر. الحمد لله لم يُصب أحد.
شاكرةً لكم،
هيا
```

My answer:

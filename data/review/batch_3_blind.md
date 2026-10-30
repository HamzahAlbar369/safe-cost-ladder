# Review batch 3 — blind (no gold)

> FICTIONAL insurer and synthetic tickets; dev split only (held-out is never shown). Items: the 50 from dev_review.md (selection seed `20261030:review`), batched with seed `20261030:review-batches`.

Write your answer for each item, then compare with `batch_3_gold.md`.

## dev-0183 · English · extract

```text
hello there
I'm insured with you under policy OMI-8392971 (comprehensive), which runs until 13/08/2026.
I have been your customer for 6 years.
I'm filing the claim today, 02/04/2026.
It was raining a little that eevning.
My car is a Nissan Patrol 2022.
The accident was reported to Najm; the report number is NJ-76220189.
A few days ago another car hit mine in Riyadh, and it turned out the other driver had no insurance.
thanks
```

My answer:

## dev-0306 · Arabic · adjudicate

```text
[نموذج مطالبة إلكتروني]
رقم الpolicy: OMI-8188048
نوع التغطية: تأمين شامل (COMP)
تاريخ الانتهاء: 2026-06-03
نوع المطالبة: مطالبة طرف ثالث ضدي
الطرف الآخر: معروف ومؤمَّن عليه
تاريخ وقوع الحادث: 2026-02-20
جهة الإبلاغ: نجم
رقم تقرير الحادث: NJ-23576349
نسبة خطئي: 50%
أضرار الطرف الآخر حسب التقييم: 41,400 ريال
تاريخ الإرسال: 2026-03-05
وصف الحادث: في 2026-02-20 وقع لي حادث في تبوك، والطرف الآخر عبدالله يطالب بالتعويض من وثيقتي. مرفق: report الحادث من نجم، رخصة سير المركبة (الاستمارة)، نسخة من رخصة القيادة، صور التلفيات وتقرير تقدير (Taqdeer). أنا عميل لديكم منذ 8 سنوات.
```

My answer:

## dev-0266 · Arabic · intent

```text
هذه تفاصيل حالتي.
اسمي يوسف. لا أوافق على نسبة الخطأ في التقرير NJ-53455912، فقد كنت متوقفًا عند الإشارة.
أرجو إفادتي.
```

My answer:

## dev-0223 · English · adjudicate

```text
[Web form submission]
Policy number: OMI-1262800
Cover type: comprehensive (COMP)
Expiry date: 2027-05-17
Claim type: own damage
Other party: identified, insured
Date of accident: 2026-07-24
Reporting authority: Najm
Accident report number: NJ-55068547
My fault share: 0%
Sum insured: 170,000 SAR
Date submitted: 2026-08-07
Description: On 2026-07-24 another car hit mine in Tabuk. The garage quoted 21,700 SAR for the repairs; I don't have a damage assessment report yet. Attached are the Najm accident report, the istimara, the licence copy and the damage photos. the Taqdeer assessment is still not ready. My claim reference from the app is CLM-49911.
```

My answer:

## dev-0135 · Arabic · intent

```text
هذه تفاصيل حالتي.
أكتب إليكم من تبوك. الوثيقة OMI-4899080. كيف أبدأ مطالبة؟ صُدمت سيارتي أمس ولم أبلغكم بعد.
ما الإجراء التالي؟
```

My answer:

## dev-0048 · Arabic · adjudicate

```text
[طلب عبر الموقع]
رقم الpolicy: OMI-3493774
نوع التغطية: تأمين شامل (COMP)
تاريخ الانتهاء: 2027-06-08
نوع الclaim: أضرار ذاتية
الطرف الآخر: معروف ومؤمَّن عليه
تاريخ وقوع الحادث: 2026-08-25
جهة الإبلاغ: نجم
رقم report الحادث: NJ-44124673
نسبة خطئي: 75%
تكلفة الإصلاح حسب تقرير التقييم: 22,500 ريال
مبلغ التأمين: 119,000 ريال
تاريخ الإرسال: 2026-08-27
وصف الحادث: بتاريخ 2026-08-25 صدمت سيارةٌ أخرى سيارتي في حائل. لم يكن لدى السائق رخصة قيادة. مرفق: report الحادث من نجم، رخصة سير المركبة (الاستمارة)، نسخة من رخصة القيادة، صور التلفيات وتقرير تقدير (Taqdeer). أنا عميل لديكم منذ 3 سنوات. الحمد لله لم يُصب أحد.
```

My answer:

## dev-0326 · English · adjudicate

```text
Dear Oasis claims team,
My policy number is OMI-4133235 and I have comprehensive (COMP) cover, valid until 18 May 2026. On 25 April 2026 I was in a collision with another vehicle in Dammam. The traffic police attended and issued report TP-68792556, which puts me at 25% fault. The Taqdeer assessment values the repairs to my car at SAR 22,500. The sum insured on my schedule is SAR 94,000. Nasser, who works in our home was driving at the time. I am reporting this claim to you on 9 May 2026. I have attached the traffic police report, the vehicle registration, a copy of the driving licence, photos of the damage and the damage assessment report. My car is a Chevrolet Tahoe 2021. I have been your customer for 5 years.
Thank you,
Nasser
```

My answer:

## dev-0078 · English · faq

```text
Good morning,
My name is Khalid and I drive a Hyundai Sonata 2020. Up to how much is towing covered outside the city?
Kind regards,
Khalid
```

My answer:

## dev-0270 · English · adjudicate

```text
I need to tell you what happened.
I'm insured with you under policy OMI-4758337 (comprehensive), which runs until 22 August 2026. I am reporting this claim to you on 27 July 2026. The Najm report number is NJ-38285890 and it gives me 0% of the liability. The Taqdeer assessment values the repairs to my car at 98,900 SAR. On 17 July 2026 I was in a collision with another vehicle in Khobar. I was the one driving. My car is insured for 84,000 SAR. I have attached the Najm report, the vehicle registration, a copy of the driving licence, photos of the damage and the damage assessment report. It was raining a little that evening.
Please advise.
```

My answer:

## dev-0282 · English · adjudicate

```text
Here is my situation.
I'm insured with you under policy OMI-1116741 (comprehensive), which runs until 24 June 2026. On 1 March 2026 I hit another car in Khobar. The other driver, Turki, is claiming against my policy. The traffic police report number is TP-61217050 and it gives me 75% of the liability. The damage assessment report for the other car comes to 24,600 SAR. The licence had expired (1 January 2026); it was renewed on 25 April 2026. so I first reporetd this claim to you on 12 March 2026. Attached are the traffic police accident report, the istimara, the licence copy, the damage photos and the Taqdeer assessment. It was raining a little that evening, yalla. My previous claim in 2023 was settled without any problem.
Please advise.
```

My answer:

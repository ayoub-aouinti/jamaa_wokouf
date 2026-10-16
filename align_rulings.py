#!/usr/bin/env python3
"""محاذاة أسطر الأحكام المستخرجة على فهرس المصحف، وإسقاطُ ما لا ينطبق.

صيغة السطر: الصفحة | اللفظ القرآني | المصطلح | 0/1 للنفي | القائل
والمحاذاةُ هي الضبط: لفظٌ لا يوجد في المصحف يسقط، فلا يدخل القاعدةَ موضعٌ
مختلَق ولا محرَّف.
"""
import csv, glob, json, re, sys
from collections import Counter
from locator import Locator
from normalize import norm

# ترتيب الفحص مقصود: ألفاظ المنع أولاً، لئلا يُقرأ «ليس بوقف كافٍ» كفايةً
SYM = [
    ('لا', r'(ليس بوقف|ليس بقطع|لا يوقف|لا تقف|لا تقفن|لا يقف|ليس بموضع|'
           r'لم يتم|لا يتم|لم تقف|ليس بتمام|ليس بكاف|ليس بكافي|غير تام|'
           r'لا يحسن|ليس بحسن|ليس بصالح|لا يجوز|ليست بآية|ليس بآية|'
           # نفيُ الدانيِّ في «المكتفى»: «لم يكف» و«لم يقف عليه»
           r'لم يكف|لا يكفي|لم يقف|'
           # ثغرةٌ كانت تُقرأ إثباتاً: «ليس بتام» غيرُ «ليس بتمام»، و«لم يكن
           # تاماً» و«دون تمام» و«لا وقف دونه» نفيٌ كلُّها. وحقلُ النفي في
           # الاستخراج يسترها، لكنْ لا يُترك البابُ مفتوحاً على حقلٍ قد يُغفَل.
           r'ليس بتام|ليس بكافٍ|لم يكن تام|لم يكن الوقف|دون تمام|'
           r'لا وقف دونه|لا يقطع|لم يوقف|ليس قبله وقف|ليس بعده وقف)'),
    # القبيح مرتبةٌ قائمة عند ابن الأنباري وغيره، لا هي المنع المجرَّد،
    # فتُفرد برمزها ويُحفظ لفظُها كما هو
    ('ق', r'(قبيح|أقبح|اقبح|قبح)'),
    # صيغُ التفضيل في الحُسن («أتمّ حُسناً»، «أحسن منه»، «حِسان») حُسنٌ لا تمام،
    # فتُقدَّم على قاعدة التمام لئلا تُقرأ «أتمّ حسناً» تماماً
    ('ح', r'(حسنا|حسان|حسنان|أحسن|احسن|حسني)'),
    ('ت', r'(تمام|تام|أتم|اتم|تم الكلام|^تم$|^يتم$)'),
    # عبارةُ الدانيِّ في الكفاية: «أكفى» و«أكفى منه» و«كفى» و«يكفي»، وهي
    # صيغُ تفضيلٍ في الكفاية لا مرتبةٌ أخرى. وقد سُبقت بالنفي أعلاه لئلا
    # تُقرأ «لا يكفي» كفايةً.
    ('ك', r'(كاف|كافي|كافٍ|الكافي|أكفى|اكفى|كفى|يكفي|تكفي)'),
    ('ح', r'(حسن|أحسن|احسن)'),
    # «أصلح» صيغةُ تفضيلٍ في الصلاح، وهي مرتبةُ الصالح لا مرتبةٌ أخرى
    ('ص', r'(صالح|أصلح|اصلح)'),
    # «وقف سنة»: ما وقف عليه النبي ﷺ. وهو أكثرُ ما في «منازل القرآن»،
    # ومرتبةٌ قائمةٌ برأسها لا تُردّ إلى غيرها
    ('سن', r'(سنة|سنه|سنتان|سنن)'),
    ('آ', r'(آية|اية|آيتان|رأس آية)'),
    ('ج', r'(جائز|جايز|يجوز|وإن شئت|ان شيت)'),
    ('لز', r'(لازم)'),
    # «وقف البيان» رابعُ أنواع الوقف عند ابن الغزّال
    ('ب', r'(البيان|بيان)'),
    # «مختار» و«أحسن منه» إثباتُ وقفٍ بلا تسمية مرتبة
    ('و', r'(مختار|أحسن منه|احسن منه)'),
    ('مف', r'(مفهوم)'),
    # «القطع» و«الوقف» مجرَّدين، وصيغُ الأمر بالوقف: إثباتُ وقفٍ بلا تسمية مرتبة
    ('و', r'(القطع|قطع|الوقف|وقف|يقطع|فالقطع|هاهنا|^قف|^تقف|^يقف|^نقف)'),
]
SYM = [('شت', r'(شبه التام|شبه التمام)')] + SYM
SYM_RE = [(s, re.compile(p)) for s, p in SYM]

# كتبٌ تختصر المرتبة بحرفٍ واحد. والحرفُ الواحد يختلف معناه بين الكتب:
# (م) عند السجاوندي لازمٌ وعند ابن الغزّال تامّ، و(ص) عند السجاوندي مرخَّصٌ
# لضرورة وعند غيره صالح. فلكلِّ كتابٍ جدولُه في symbols.json بشاهده، ولا
# يُحمَل حرفُ كتابٍ على معناه في غيره. وتُطابَق على تمام اللفظ لا على جزءٍ
# منه، لئلا يلتبس الحرفُ بكلمةٍ فيها.
_SYMS = json.load(open('symbols.json', encoding='utf-8'))
EXACT = _SYMS['_default']['map']


# المؤلفُ الواحدُ يسمّي العالمَ الواحدَ بكُنيته ونسبته ووصفه بكتابه، فيصير
# الرجلُ في القاعدة رجالاً: «أبو بكر» و«صاحب أبي حاتم» و«ابن الأنباري» ثلاثةُ
# أسماءٍ لواحد. فتُوحَّد بجدولٍ لكل كتابٍ بشاهده في sayers.json — **ولا يُمحى
# لفظُ الكتاب**، بل يُثبَت في العلّة «وفي الكتاب: كذا»، فالتوحيدُ للجمع لا
# للتصحيح، ويبقى نصُّ المؤلف قابلاً للمراجعة.
_SAYERS = json.load(open('sayers.json', encoding='utf-8'))
SAYER_MAP = {}
SAYER_PULL = ()


def use_book(book_id):
    """تثبيتُ جدولَي الحروف والقائلين لكتابٍ بعينه قبل المحاذاة."""
    global EXACT, SAYER_MAP, SAYER_PULL
    tab = _SYMS.get(book_id)
    if tab:
        EXACT = tab['map']
        print(f"جدولُ الحروف: {book_id} — حجّتُه: {tab.get('_حجة', 'غير مذكورة')}")
    else:
        print(f'تنبيه: لا جدولَ حروفٍ لـ{book_id}؛ استُعمل الجدولُ العامّ، وهو ظنٌّ لا تصريح.')
    stab = _SAYERS.get(book_id)
    if stab and stab.get('map'):
        SAYER_MAP = stab['map']
        print(f"جدولُ القائلين: {book_id} — {len(SAYER_MAP)} اسماً — "
              f"حجّتُه: {stab.get('_حجة', 'غير مذكورة')}")
    else:
        SAYER_MAP = {}
        print(f'لا جدولَ قائلين لـ{book_id}؛ تُترَك الأسماءُ على ألفاظها.')
    SAYER_PULL = tuple((stab or {}).get('_انتزاع', ()))
    if SAYER_PULL:
        print('أسماءٌ تُنتزَع من العلّة إن خلا حقلُ القائل:', '، '.join(SAYER_PULL))


def norm_sayer(s):
    """يردُّ (الاسمَ الموحَّد، لفظَ الكتاب إن خالفه)."""
    s = (s or '').strip()
    if not s or s == '-':
        return '', None
    canon = SAYER_MAP.get(s)
    if canon and canon != s:
        return canon, s
    return canon or s, None


# ردُّ المؤلفِ قولَ غيره ليس حكمَ وقف. فـ«ليس كذلك» و«خطأ» و«لا وجه له»
# تخطئةٌ لقائلٍ، لا نفيٌ للوقف في الموضع. ولو رُدَّت إلى «ليس بوقف» لانقلب
# «هذا العالمُ مخطئ» إلى «لا تقف هنا»، وهما خبران مختلفان. فتُطرَح صريحاً.
REJECT = re.compile(r'(ليس كذلك|ليس كما قال|ليس كما قالوا|ليس بشيء|'
                    r'ليس ذلك بشيء|ليس يصح|لا وجه له|^خطأ$|'
                    r'^الاختيار$|^استأنف)')


def symbol_of(term):
    t = (term or '').strip()
    if REJECT.search(t):
        return None
    if t in EXACT:
        return EXACT[t]
    n = norm(term)
    for s, rx in SYM_RE:
        if rx.search(term) or rx.search(n):
            return s
    return None


def sura_of(page, starts):
    cur = None
    for p, s in starts:
        if page >= p:
            cur = s
        else:
            break
    return cur


def suras_on(page, starts):
    """مجموعةُ السور المحتملة في صفحةٍ واحدة، لا سورةٌ واحدة.

    كتابٌ كـ«المكتفى» يُفرِد لكل سورةٍ صفحاتٍ، فالصفحةُ تدلّ على سورتها.
    و«المقصد» يختصر القرآن في إحدى وثمانين صفحة، فتجتمع في الصفحة الواحدة
    أربعُ سورٍ وأكثر. فحملُ الصفحةِ على سورةٍ واحدةٍ يُضِلُّ المحاذاةَ في
    هذا النوع بدل أن يَهديها: يُقصِر الاحتمالَ على سورةٍ ليس الموضعُ فيها.

    فالقيدُ هنا مدًى: من السورة التي ابتدأت في هذه الصفحة أو قبلها، إلى
    آخر سورةٍ تبتدئ فيها.
    """
    prev = None                      # السورةُ الجاريةُ عند أول الصفحة
    for p, s in starts:
        if p < page:
            prev = s
        else:
            break
    on = [s for p, s in starts if p == page]    # ما ابتدأ في الصفحة نفسِها
    if not on:
        return (prev, prev)
    lo = prev if prev is not None else on[0]
    return (lo, max(on))


def main(pattern, suras_json, out_csv, book_id=None):
    if book_id:
        use_book(book_id)
    loc = Locator('out/words_indexed.json')
    starts = json.load(open(suras_json, encoding='utf-8'))['starts']
    rows, dropped, unified, dupes = [], Counter(), Counter(), 0
    state = {'last': -1, 'sura': None}
    lines = []
    for path in sorted(glob.glob(pattern)):
        for ln in open(path, encoding='utf-8'):
            ln = ln.strip()
            if not ln or ln.count('|') < 4:
                continue
            lines.append(ln)
    # الكتاب يمشي على ترتيب المصحف، فيُرتَّب المدخل على الصفحات
    def pageno(ln):
        try:
            return int(ln.split('|')[0].strip())
        except ValueError:
            return 10 ** 9
    lines.sort(key=pageno)

    # رمزان فأكثر على لفظٍ واحد («م ك») حكمان لا حكمٌ واحد، فيُفصلان
    split = []
    for ln in lines:
        parts = [x.strip() for x in ln.split('|')]
        toks = parts[2].split() if len(parts) > 2 else []
        # «ج ز» في موضعٍ واحدٍ عند السجاوندي حكمان لا حكمٌ مركَّب، فيُفصلان.
        # وزيدت ز وط لرموزه، لئلا يسقط الموضعُ بدعوى أن رمزَه غيرُ معروف.
        if len(toks) > 1 and all(len(t) == 1 and t in 'حكمتبصجقزط' for t in toks):
            for t in toks:
                split.append('|'.join([parts[0], parts[1], t] + parts[3:]))
        else:
            split.append(ln)
    lines = split

    # صفحةٌ مُسِحت مرّتين تُخرِج أسطراً متطابقةً حرفاً بحرف (صفحتا الـPDF ٥ و٦
    # من الجزء الثالث كلتاهما «٦٢٧»). والسطرُ المتطابقُ في صفحةٍ واحدةٍ لفظاً
    # ومرتبةً وقائلاً وآيةً وعلّةً تكرارُ مسحٍ أو طبعٍ لا حكمان، فيُطرَح الثاني.
    seen_ln, uniq = set(), []
    for ln in lines:
        key = ln.strip()
        if key in seen_ln:
            dupes += 1
            continue
        seen_ln.add(key)
        uniq.append(ln)
    lines = uniq

    for ln in lines:
        parts = [x.strip() for x in ln.split('|')]
        page_s, quote, term, neg_s, sayer = parts[0], parts[1], parts[2], parts[3], parts[4]
        # بعضُ الكتب تُثبت رقمَ الآية مع كل موضع، كـ«علل الوقوف» للسجاوندي:
        # ﴿للمتقين- ٢ - لا﴾. وهو إحداثيٌّ ثانٍ يقطع الاشتباهَ في المتكرِّر،
        # فيُقبل حقلاً سادساً اختيارياً ويُهمَل إن لم يكن رقماً.
        # الحقلُ السابع علّةُ الوقف بلفظ المؤلف، كما في «علل الوقوف»
        # للسجاوندي. وهي أنفسُ ما في الكتاب، فتُنقل كما هي ولا تُلخَّص.
        reason = parts[6].strip() if len(parts) > 6 else ''
        sayer, said_as = norm_sayer(sayer)
        if said_as:
            reason = (reason + ' · ' if reason else '') + f'وفي الكتاب: {said_as}'
            unified[f'{said_as} ← {sayer}'] += 1
        # عزوٌ وقع في العلّة وحقلُ القائل فارغ: يُنتزَع ويُرَدُّ إلى موضعه،
        # لئلا يُحسَب قولُ المعزوِّ إليه قولاً لصاحب الكتاب. والعلّةُ باقية.
        # ويلحق به «غيره»، فهي حقلُ مَن لم يُعرَف، ولا يُبهَم المعلومُ إبهامَ
        # المجهول. ولفظُ الكتاب باقٍ في العلّة، فالانتزاعُ مراجَعٌ لا مطموس.
        if sayer in ('', 'غيره') and reason:
            for nm in SAYER_PULL:
                if nm in reason:
                    was = sayer or 'فارغ'
                    sayer = norm_sayer(nm)[0]
                    unified[f'انتُزع من العلّة ({was}) ← {sayer}'] += 1
                    break
        ayah_hint = None
        if len(parts) > 5 and parts[5]:
            a = parts[5].translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
            if a.isdigit():
                ayah_hint = int(a)
        try:
            page = int(page_s)
        except ValueError:
            dropped['صفحة غير رقمية'] += 1
            continue
        sym = symbol_of(term)
        if sym is None:
            dropped['مصطلح غير معروف'] += 1
            continue
        neg = neg_s.strip() in ('1', 'نعم', 'true', 'True')
        qt = [t for t in (norm(w) for w in quote.split()) if t]
        if not qt or len(qt) > 25:
            dropped['لفظ فارغ أو مفرط الطول'] += 1
            continue
        hits = loc.match_seq(qt)
        loose = skel = False
        if not hits:
            # الرسم الإملائي مقابل العثماني: «الصراط» في المصحف «الصرٰط»،
            # و«الكتاب» «الكتٰب». وأكثرُ ما يفوت بهذا الكلماتُ المفردة،
            # وهي عامّةُ ما يقتبسه ابنُ الأنباري وأمثاله.
            hits = loc.match_seq_loose(qt)
            loose = bool(hits)
        if not hits:
            # آخرُ المراتب: الهيكلُ الصامت، لطائفةِ «الصلاة/الصلوة». وهو
            # تساهلٌ شديد، فيُشترَط فيه أن يتفرَّد الموضعُ في سورته، وإلا
            # طُرح. فالمشتبِهُ هنا أسوأُ من المفقود.
            cand = loc.match_seq_skel(qt)
            if cand:
                s0 = sura_of(page, starts)
                inside = [h for h in cand if s0 and loc.w[h]['sura'] == s0]
                if len(inside) == 1:
                    hits, loose, skel = inside, True, True
        if not hits:
            dropped['لا يطابق المصحف'] += 1
            continue
        sura = sura_of(page, starts)
        if sura != state['sura']:
            state['sura'], state['last'] = sura, -1
        # القيدُ مدى السور المحتملة في الصفحة لا سورةً واحدة
        lo, hi = suras_on(page, starts)
        ins = [h for h in hits
               if lo is None or lo <= loc.w[h]['sura'] <= (hi if hi else lo)]
        use = ins or hits
        # رقمُ الآية يُقدَّم على القرائن كلِّها: فإن وافق موضعاً واحداً انقطع
        # الاشتباه. وإن لم يوافق شيئاً فالرقمُ أو اللفظُ محرَّف، فيُترك الرقم
        # ولا يُطرح الموضعُ به — الطرحُ للمحاذاة لا للترقيم.
        ayah_ok = False
        if ayah_hint is not None:
            exact = [h for h in use if loc.w[h]['ayah'] == ayah_hint]
            if exact:
                use, ins, ayah_ok = exact, exact, True
        fwd = [h for h in use if h >= state['last'] - 40]
        use = fwd or use
        n = len(use)
        pos = loc.seq_position(use[0], len(qt))
        # الحاسمُ تفرّدُ الموضع داخل سورته، لا طولُ اللفظ: كلمةٌ لا تتكرر
        # في سورتها أدلُّ من ثلاثٍ تتكرر فيها
        if len(ins) == 1:
            conf = 'عالية'
        elif n == 1 or len(qt) >= 4:
            conf = 'متوسطة'
        else:
            conf = 'تحتاج مراجعة'
        if ayah_ok and len(use) == 1:
            conf = 'عالية'                       # لفظٌ وآيةٌ اتفقا: لا يبقى احتمال
        if loose and conf == 'عالية':
            conf = 'متوسطة'                      # مطابقةٌ متساهلة لا تُعدّ يقيناً
        if skel:
            conf = 'تحتاج مراجعة'                # الهيكلُ الصامت ظنٌّ لا يُعتمد
        if conf != 'تحتاج مراجعة':
            state['last'] = max(state['last'], use[0])
        rows.append({
            'page': page, 'quote': quote, 'term': term, 'negated': int(neg),
            'symbol': 'لا' if neg else sym, 'sayer': sayer if sayer != '-' else '',
            'seq': pos['end_seq'], 'sura': pos['sura'], 'ayah': pos['ayah'],
            'sura_name': pos['sura_name'], 'stop_word': pos['stop_word'],
            'words': len(qt), 'candidates': n, 'conf': conf, 'loose': int(loose),
            'sura_book': sura, 'sura_lo': lo, 'sura_hi': (hi if hi else lo),
            'ayah_book': ayah_hint or '', 'ayah_ok': int(ayah_ok),
            'skel': int(skel), 'reason': reason,
        })
    with open(out_csv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print('مدخلات:', len(lines), '· مقبولة:', len(rows))
    print('مسقَطات:', dict(dropped))
    if dupes:
        print('أسطرٌ متطابقةٌ طُرِحت (تكرارُ مسحٍ أو طبع):', dupes)
    print('الثقة:', Counter(r['conf'] for r in rows))
    if unified:
        print('أسماءٌ وُحِّدت (ولفظُ الكتاب محفوظٌ في العلّة):',
              ' · '.join(f'{k}: {v}' for k, v in unified.most_common()))
    # المقياسُ مدى الصفحة لا سورةٌ واحدة، وإلا ظُلِم الكتابُ الكثيف:
    # صفحةُ «المقصد» الواحدة تسع تسعَ سور، فمطابقةُ سورةٍ بعينها ليست شرطاً.
    inrange = sum(1 for r in rows if r['sura_lo'] and
                  r['sura_lo'] <= r['sura'] <= r['sura_hi'])
    print('الموضع داخل مدى سور صفحته:', inrange, '/', len(rows),
          f'({100 * inrange // max(1, len(rows))}%)')
    hinted = [r for r in rows if r['ayah_book'] != '']
    if hinted:
        print('فيها رقم آية:', len(hinted), '· وافق الرقمُ موضعاً واحداً:',
              sum(1 for r in hinted if r['ayah_ok']), '· وخالف أو لم يُفد:',
              sum(1 for r in hinted if not r['ayah_ok']))


if __name__ == '__main__':
    main(*sys.argv[1:5])

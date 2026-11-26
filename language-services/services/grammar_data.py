"""Curated grammar facts that a learner must be able to trust, so they are not left to a language model.

Sources: the standard verb-pattern lists in learner grammars (Murphy, English Grammar in Use units 53-58;
Swan, Practical English Usage 'verb + -ing or infinitive'), checked one by one. A verb missing here is answered
by the model and marked as such in the API ("source": "model").
"""

# kind -> verbs. Keys are the API values of complement.kind.
COMPLEMENT = {
    "gerund": [
        "admit", "anticipate", "appreciate", "avoid", "celebrate", "consider", "delay", "deny", "detest", "discuss",
        "dislike", "endure", "enjoy", "escape", "excuse", "fancy", "finish", "imagine", "involve", "justify", "keep",
        "mention", "mind", "miss", "postpone", "practice", "practise", "quit", "recall", "resent", "resist", "resume",
        "risk", "suggest", "tolerate", "give up", "put off", "carry on", "keep on", "end up", "look forward to",
        "feel like", "can't help", "can't stand", "object to", "get used to", "be used to",
    ],
    "infinitive": [
        "afford", "agree", "aim", "appear", "arrange", "attempt", "choose", "claim", "consent", "decide", "demand",
        "deserve", "expect", "fail", "guarantee", "happen", "hesitate", "hope", "learn", "manage", "offer", "plan",
        "prepare", "pretend", "promise", "proceed", "prove", "refuse", "seem", "struggle", "swear", "tend", "threaten",
        "volunteer", "wait", "want", "wish", "would like", "would love", "would prefer", "determine", "intend",
    ],
    "object + infinitive": [
        "advise", "allow", "cause", "encourage", "enable", "force", "get", "instruct", "invite", "order", "permit",
        "persuade", "remind", "require", "teach", "tell", "urge", "warn",
    ],
    "both, same meaning": ["begin", "start", "continue", "hate", "like", "love", "prefer", "can't bear", "bother", "cease"],
    "both, different meaning": ["stop", "remember", "forget", "try", "regret", "go on", "mean", "need"],
    "bare infinitive": ["let", "make", "had better", "would rather", "help"],
    "modal": ["can", "could", "may", "might", "must", "shall", "should", "will", "would", "ought to"],
}

# Short rule per kind, English and Turkish.
COMPLEMENT_RULE = {
    "gerund": ("Followed by the -ing form, never by to + verb.", "Arkasından fiilin -ing hali gelir; to + fiil gelmez."),
    "infinitive": ("Followed by to + verb.", "Arkasından to + fiil gelir."),
    "object + infinitive": ("Followed by an object + to + verb (tell someone to do).",
                            "Arkasından nesne + to + fiil gelir (birine bir şey yapmasını söylemek)."),
    "both, same meaning": ("Takes either -ing or to + verb with almost the same meaning.",
                           "Hem -ing hem to + fiil alır; anlam neredeyse aynıdır."),
    "both, different meaning": ("Takes -ing or to + verb, and the meaning changes.",
                                "Hem -ing hem to + fiil alır ama anlam değişir."),
    "bare infinitive": ("Followed by the base form without to (let him go).", "Arkasından to olmadan yalın fiil gelir (let him go)."),
    "modal": ("A modal verb: followed by the base form without to, no -s, no -ing.",
              "Kip fiili: arkasından to olmadan yalın fiil gelir; -s, -ing almaz."),
}

# The meaning difference for 'both, different meaning' verbs: (form, meaning en, meaning tr, example).
DIFFERENT_MEANING = {
    "stop": [("stop doing", "quit an activity", "bir şeyi yapmayı bırakmak", "She stopped smoking last year."),
             ("stop to do", "pause in order to do something else", "başka bir şey yapmak için durmak", "He stopped to buy some water.")],
    "remember": [("remember doing", "have a memory of an earlier action", "yapmış olduğunu hatırlamak", "I remember locking the door."),
                 ("remember to do", "not forget a task", "yapmayı unutmamak", "Remember to lock the door.")],
    "forget": [("forget doing", "lose the memory of an earlier action (mostly negative)", "yaptığını unutmak", "I'll never forget meeting her."),
               ("forget to do", "not do something you should do", "yapmayı unutmak", "I forgot to call my mother.")],
    "try": [("try doing", "do something as an experiment", "denemek için yapmak", "Try restarting the computer."),
            ("try to do", "make an effort", "yapmaya çalışmak", "I tried to open the window, but it was stuck.")],
    "regret": [("regret doing", "be sorry about something you did", "yaptığına pişman olmak", "I regret saying that."),
               ("regret to do", "be sorry to announce bad news (formal)", "üzülerek bildirmek", "We regret to inform you that the flight is cancelled.")],
    "go on": [("go on doing", "continue the same activity", "aynı şeyi yapmaya devam etmek", "She went on talking for hours."),
              ("go on to do", "move to a new activity", "ardından başka bir şeye geçmek", "After the intro, he went on to explain the plan.")],
    "mean": [("mean doing", "involve as a result", "anlamına gelmek, gerektirmek", "A new job would mean moving to London."),
             ("mean to do", "intend", "niyetinde olmak", "I didn't mean to hurt you.")],
    "need": [("need doing", "need to be done (passive meaning)", "yapılması gerekmek", "The car needs washing."),
             ("need to do", "it is necessary for you to do", "yapması gerekmek", "I need to wash the car.")],
}

# Verbs that are normally stative: not used in continuous tenses in their main meaning.
STATIVE = {
    "believe", "belong", "consist", "contain", "cost", "depend", "deserve", "doubt", "hate", "include", "involve", "know",
    "lack", "like", "love", "matter", "mean", "need", "owe", "own", "possess", "prefer", "realise", "realize",
    "recognise", "recognize", "remember", "forget", "seem", "suppose", "understand", "want", "wish", "hear", "agree",
    "disagree", "mind", "surprise", "impress", "astonish", "concern", "resemble", "fit",
}
# Stative in one meaning, dynamic (continuous is fine) in another.
STATIVE_AND_DYNAMIC = {
    "think": ("'I think (that)...' = opinion: no continuous. 'I'm thinking about...' = considering: continuous is fine.",
              "'I think' = fikir: süreklilik yok. 'I'm thinking about' = üzerinde düşünmek: süreklilik olur."),
    "have": ("'have' = own: no continuous. 'have breakfast / a shower / fun': continuous is fine.",
             "'have' = sahip olmak: süreklilik yok. 'have breakfast/a shower': süreklilik olur."),
    "see": ("'see' = notice with the eyes: no continuous. 'I'm seeing a friend' = meeting: continuous is fine.",
            "'see' = görmek: süreklilik yok. 'I'm seeing a friend' = buluşmak: süreklilik olur."),
    "taste": ("'It tastes good' = quality: no continuous. 'I'm tasting the soup' = action: fine.",
              "'tastes good' = tadı güzel: süreklilik yok. 'tasting the soup' = tadına bakmak: olur."),
    "smell": ("'It smells nice' = quality: no continuous. 'She's smelling the flowers' = action: fine.",
              "'smells nice' = kokusu güzel: süreklilik yok. 'smelling the flowers' = koklamak: olur."),
    "feel": ("'I feel (that)...' = opinion: no continuous. 'I'm feeling tired' = state of the body: both are fine.",
             "'I feel that' = fikir: süreklilik yok. 'I'm feeling tired': ikisi de olur."),
    "look": ("'You look tired' = seem: no continuous. 'I'm looking at the map' = action: fine.",
             "'You look tired' = görünmek: süreklilik yok. 'looking at' = bakmak: olur."),
    "appear": ("'He appears to be ill' = seem: no continuous. 'She's appearing in a film' = perform: fine.",
               "'appears to be' = görünmek: süreklilik yok. 'appearing in a film' = rol almak: olur."),
    "weigh": ("'It weighs 5 kg' = quality: no continuous. 'I'm weighing the flour' = action: fine.",
              "'weighs 5 kg' = ağırlığı olmak: süreklilik yok. 'weighing the flour' = tartmak: olur."),
    "be": ("'He is rude' = character: no continuous. 'He is being rude' = behaving so right now: fine.",
           "'He is rude' = kişilik. 'He is being rude' = şu an öyle davranıyor."),
    "imagine": ("'I imagine (that)...' = suppose: no continuous. 'I'm imagining a beach' = picture it: fine.",
                "'I imagine that' = sanmak: süreklilik yok. 'imagining a beach' = hayal etmek: olur."),
    "expect": ("'I expect (that)...' = think: no continuous. 'We're expecting a baby / guests' = wait for: fine.",
               "'I expect that' = sanmak: süreklilik yok. 'expecting guests' = beklemek: olur."),
    "measure": ("'The room measures 5 m' = size: no continuous. 'I'm measuring the room' = action: fine.",
                "'measures 5 m' = ölçüsü olmak. 'measuring the room' = ölçmek: olur."),
    "consider": ("'I consider him a friend' = regard: no continuous. 'I'm considering the offer' = think about: fine.",
                 "'consider him a friend' = saymak. 'considering the offer' = düşünmek: olur."),
}

MODALS = set(COMPLEMENT["modal"])


def complement_of(lemma):
    """('kind', source) for a verb or phrase, or (None, None) when it is not in the curated lists."""
    for kind, verbs in COMPLEMENT.items():
        if lemma in verbs:
            return kind, "curated"
    return None, None


def aspect_of(lemma):
    """'stative', 'both' (with a note) or 'dynamic'."""
    if lemma in STATIVE_AND_DYNAMIC:
        return "both"
    if lemma in STATIVE:
        return "stative"
    return "dynamic"

# Verbs whose forms depend on the meaning or the variety, where a lexicon's first form would mislead.
FORM_OVERRIDES = {
    "lie": {"past simple": "lay (= lie down) / lied (= say something untrue)",
            "past participle": "lain (= lie down) / lied (= say something untrue)"},
    "hang": {"past simple": "hung / hanged (= kill by hanging)", "past participle": "hung / hanged (= kill by hanging)"},
    "get": {"past participle": "got (UK) / gotten (US)"},
    "learn": {"past simple": "learned / learnt (UK)", "past participle": "learned / learnt (UK)"},
    "dream": {"past simple": "dreamed / dreamt (UK)", "past participle": "dreamed / dreamt (UK)"},
    "burn": {"past simple": "burned / burnt (UK)", "past participle": "burned / burnt (UK)"},
    "spell": {"past simple": "spelled / spelt (UK)", "past participle": "spelled / spelt (UK)"},
    "smell": {"past simple": "smelled / smelt (UK)", "past participle": "smelled / smelt (UK)"},
    "spoil": {"past simple": "spoiled / spoilt (UK)", "past participle": "spoiled / spoilt (UK)"},
    "lean": {"past simple": "leaned / leant (UK)", "past participle": "leaned / leant (UK)"},
    "leap": {"past simple": "leaped / leapt", "past participle": "leaped / leapt"},
    "dive": {"past simple": "dived / dove (US)", "past participle": "dived"},
    "prove": {"past participle": "proved / proven"},
    "wake": {"past simple": "woke", "past participle": "woken"},
}

MODAL_PAST = {"can": "could", "may": "might", "will": "would", "shall": "should"}

# Words that take a fixed preposition: (preposition phrase, Turkish meaning). The core of the "prepositions" section;
# after any of these prepositions a verb takes -ing (interested in learning, depend on getting).
PREPOSITIONS = {
    # verbs
    "depend": [("depend on", "-e bağlı olmak")], "rely": [("rely on", "-e güvenmek, -e dayanmak")],
    "insist": [("insist on", "-de ısrar etmek")], "concentrate": [("concentrate on", "-e odaklanmak")],
    "focus": [("focus on", "-e odaklanmak")], "count": [("count on", "-e güvenmek")],
    "comment": [("comment on", "hakkında yorum yapmak")],
    "agree": [("agree with (someone)", "biriyle aynı fikirde olmak"), ("agree on (something)", "bir konuda anlaşmak"),
              ("agree to (a plan)", "bir şeyi kabul etmek")],
    "apologize": [("apologize for", "için özür dilemek"), ("apologize to (someone)", "birinden özür dilemek")],
    "apologise": [("apologise for", "için özür dilemek"), ("apologise to (someone)", "birinden özür dilemek")],
    "believe": [("believe in", "-e inanmak (varlığına, değerine)")], "succeed": [("succeed in", "-de başarılı olmak")],
    "participate": [("participate in", "-e katılmak")], "belong": [("belong to", "-e ait olmak")],
    "listen": [("listen to", "-i dinlemek")],
    "look": [("look at", "-e bakmak"), ("look for", "-i aramak"), ("look after", "-e bakmak, ilgilenmek"),
             ("look forward to", "-i dört gözle beklemek"), ("look up", "(sözlükte) aramak"), ("look like", "-e benzemek")],
    "wait": [("wait for", "-i beklemek")], "pay": [("pay for", "-in parasını ödemek")], "ask": [("ask for", "-i istemek")],
    "care": [("care about", "-i önemsemek"), ("care for", "-e bakmak; -i sevmek")],
    "worry": [("worry about", "için endişelenmek")],
    "think": [("think about", "hakkında düşünmek, üzerinde düşünmek"), ("think of", "aklına gelmek; hakkında fikri olmak")],
    "dream": [("dream of / about", "-i hayal etmek; rüyasında görmek")], "consist": [("consist of", "-den oluşmak")],
    "approve": [("approve of", "-i onaylamak, uygun bulmak")], "accuse": [("accuse (someone) of", "birini bir şeyle suçlamak")],
    "complain": [("complain about", "-den şikâyet etmek"), ("complain to (someone)", "birine şikâyet etmek")],
    "deal": [("deal with", "ile ilgilenmek, başa çıkmak")], "cope": [("cope with", "ile başa çıkmak")],
    "arrive": [("arrive at (a place)", "bir yere varmak (bina, istasyon)"), ("arrive in (a city/country)", "bir şehre/ülkeye varmak")],
    "laugh": [("laugh at", "-e gülmek")], "apply": [("apply for", "-e başvurmak"), ("apply to", "-e başvurmak; için geçerli olmak")],
    "search": [("search for", "-i aramak")], "prepare": [("prepare for", "-e hazırlanmak")],
    "thank": [("thank (someone) for", "birine bir şey için teşekkür etmek")],
    "blame": [("blame (someone) for", "birini bir şey için suçlamak")],
    "prevent": [("prevent (someone) from", "birinin bir şey yapmasını engellemek")],
    "stop": [("stop (someone) from", "birinin bir şey yapmasını engellemek")],
    "suffer": [("suffer from", "-den muzdarip olmak")], "recover": [("recover from", "-den iyileşmek, toparlanmak")],
    "protect": [("protect from", "-den korumak")], "borrow": [("borrow from", "-den ödünç almak")],
    "object": [("object to", "-e itiraz etmek")], "react": [("react to", "-e tepki vermek")],
    "reply": [("reply to", "-e cevap vermek")], "refer": [("refer to", "-e değinmek, -den bahsetmek")],
    "adapt": [("adapt to", "-e uyum sağlamak")], "contribute": [("contribute to", "-e katkıda bulunmak")],
    "talk": [("talk to / with", "ile konuşmak"), ("talk about", "hakkında konuşmak")],
    "speak": [("speak to / with", "ile konuşmak"), ("speak about", "hakkında konuşmak")],
    "hear": [("hear about", "hakkında duymak"), ("hear from", "-den haber almak"), ("hear of", "-in adını duymak")],
    "ask_": [], "spend": [("spend (money/time) on", "-e (para/zaman) harcamak")], "invest": [("invest in", "-e yatırım yapmak")],
    "result": [("result in", "ile sonuçlanmak"), ("result from", "-den kaynaklanmak")],
    "specialize": [("specialize in", "-de uzmanlaşmak")], "persist": [("persist in", "-de ısrar etmek")],
    "differ": [("differ from", "-den farklı olmak")], "translate": [("translate into", "-e çevirmek")],
    "divide": [("divide into", "-e bölmek")], "turn": [("turn into", "-e dönüşmek")],
    "get": [("get used to", "-e alışmak"), ("get rid of", "-den kurtulmak"), ("get on with", "ile iyi geçinmek")],
    "take": [("take care of", "-e bakmak, ilgilenmek"), ("take part in", "-e katılmak")],
    # adjectives
    "interested": [("interested in", "-e ilgili, -le ilgilenen")], "good": [("good at", "-de iyi")], "bad": [("bad at", "-de kötü")],
    "afraid": [("afraid of", "-den korkan")], "proud": [("proud of", "ile gurur duyan")], "aware": [("aware of", "-in farkında")],
    "tired": [("tired of", "-den bıkmış")], "sick": [("sick of", "-den bıkmış, usanmış")], "fond": [("fond of", "-e düşkün, -i seven")],
    "capable": [("capable of", "-e muktedir, -i yapabilecek")], "full": [("full of", "ile dolu")], "keen": [("keen on", "-e hevesli")],
    "responsible": [("responsible for", "-den sorumlu")], "famous": [("famous for", "ile ünlü")],
    "similar": [("similar to", "-e benzer")], "different": [("different from", "-den farklı")],
    "married": [("married to", "ile evli")], "angry": [("angry with (someone)", "birine kızgın"), ("angry about (something)", "bir şeye kızgın")],
    "worried": [("worried about", "için endişeli")], "excited": [("excited about", "için heyecanlı")],
    "satisfied": [("satisfied with", "-den memnun")], "familiar": [("familiar with", "-e aşina")],
    "bored": [("bored with / of", "-den sıkılmış")], "jealous": [("jealous of", "-i kıskanan")],
    "ashamed": [("ashamed of", "-den utanan")], "sure": [("sure of / about", "-den emin")], "used": [("used to", "-e alışkın")],
    "addicted": [("addicted to", "-e bağımlı")], "kind": [("kind to", "-e nazik")], "polite": [("polite to", "-e kibar")],
    "based": [("based on", "-e dayanan")], "involved": [("involved in", "-e dahil, ile uğraşan")],
    "dependent": [("dependent on", "-e bağımlı")], "independent": [("independent of", "-den bağımsız")],
    "good_": [], "nervous": [("nervous about", "için gergin")], "surprised": [("surprised at / by", "-e şaşırmış")],
    "disappointed": [("disappointed with / in", "-den hayal kırıklığına uğramış")], "pleased": [("pleased with", "-den memnun")],
    "crazy": [("crazy about", "-e deli oluyor, bayılıyor")], "busy": [("busy with", "ile meşgul")],
}
PREPOSITIONS = {k: v for k, v in PREPOSITIONS.items() if v and not k.endswith("_")}

# Patterns that need a curated verb pattern on top of the lists above.
COMPLEMENT["that-clause"] = ["think", "believe", "know", "say", "suppose", "realize", "realise", "notice", "explain",
                             "guess", "feel"]
COMPLEMENT_RULE["that-clause"] = ("Followed by a clause (that is optional): 'I think (that) it's true'. Not by to + verb.",
                                  "Arkasından bir cümle gelir ('that' isteğe bağlı): 'I think (that) it's true'. to + fiil gelmez.")
COMPLEMENT_RULE["preposition + -ing"] = ("Takes a preposition; a verb after the preposition is in the -ing form.",
                                         "Bir edatla kullanılır; edattan sonra fiil -ing alır.")

# -*- coding: utf-8 -*-
import re
import os
from os.path import join, abspath, dirname
import etoipa.eng_to_ipa.stress as stress
import sqlite3
from collections import defaultdict
import json

conn = sqlite3.connect(join(abspath(dirname(__file__)), "./resources/CMU_dict.db"))
c = conn.cursor()

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)),
                       'resources','visemes.json'), "r", encoding='utf-8') as visemes_json:
    VISEMES = json.load(visemes_json)


def preprocess(words):
    """Returns a string of words stripped of punctuation"""
    punct_str = '!"#$%&\'()*+,-./:;<=>/?@[\\]^_`{|}~«» '
    return ' '.join([w.strip(punct_str).lower() for w in words.split()])


def preserve_punc(words):
    """converts words to IPA and finds punctuation before and after the word."""
    words_preserved = []
    for w in words.split():
        punct_list = ["", preprocess(w), ""]
        before = re.search("^([^A-Za-z0-9]+)[A-Za-z]", w)
        after = re.search("[A-Za-z]([^A-Za-z0-9]+)$", w)
        if before:
            punct_list[0] = str(before.group(1))
        if after:
            punct_list[2] = str(after.group(1))
        words_preserved.append(punct_list)
    return words_preserved


def apply_punct(triple, as_str=False):
    """places surrounding punctuation back on center on a list of preserve_punc triples"""
    if type(triple[0]) == list:
        for i, t in enumerate(triple):
            triple[i] = str(''.join(triple[i]))
        if as_str:
            return ' '.join(triple)
        return triple
    if as_str:
        return str(''.join(t for t in triple))
    return [''.join(t for t in triple)]


def _punct_replace_word(original, transcription):
    """Get the IPA transcription of word with the original punctuation marks"""
    for i, trans_list in enumerate(transcription):
        for j, item in enumerate(trans_list):
            triple = [original[i][0]] + [item] + [original[i][2]]
            transcription[i][j] = apply_punct(triple, as_str=True)
    return transcription


def fetch_words(words_in):
    """fetches a list of words from the database"""
    quest = "?, " * len(words_in)
    c.execute("SELECT word, phonemes FROM dictionary WHERE word IN ({})".format(quest[:-2]), words_in)
    result = c.fetchall()
    d = defaultdict(list)
    for k, v in result:
        d[k].append(v)
    return list(d.items())


def get_cmu(tokens_in):
    """query the SQL database for the words and return the phonemes in the order of user_in"""
    result = fetch_words(tokens_in)
    ordered = []
    for word in tokens_in:
        this_word = [[i[1] for i in result if i[0] == word]][0]
        if this_word:
            ordered.append(this_word[0])
        else:
            try:
                l = word.split("'")
                if len(l) > 1:
                    to_order = get_cmu([l[0]])
                    if to_order[0][0].startswith("__IGNORE__"):
                        ordered.append([to_order[0][0] + ("$" if l[1] == "s" else "")])
                    else:
                        to_order[0][0] += ' z' if l[1] == "s" else ""
                        ordered.append(to_order[0])
                else:
                    ordered.append(["__IGNORE__" + word])
            except:
                ordered.append(["__IGNORE__" + word])
    return ordered


def cmu_to_ipa(cmu_list, mark=True, stress_marking='all'):
    """converts the CMU word lists into IPA transcriptions"""
    symbols = {"a": "ə", "ey": "e", "aa": "ɑ", "ae": "æ", "ah": "ə", "ao": "ɔ",
               "aw": "aʊ", "ay": "aɪ", "ch": "ʧ", "dh": "ð", "eh": "ɛ", "er": "ər",
               "hh": "h", "ih": "ɪ", "jh": "ʤ", "ng": "ŋ",  "ow": "oʊ", "oy": "ɔɪ",
               "sh": "ʃ", "th": "θ", "uh": "ʊ", "uw": "u", "zh": "ʒ", "iy": "i", "y": "j"}
    ipa_list = []  # the final list of IPA tokens to be returned
    for word_list in cmu_list:
        ipa_word_list = []  # the word list for each word
        for word in word_list:
            if stress_marking:
                word = stress.find_stress(word, type=stress_marking)
            else:
                if re.sub("\d*", "", word.replace("__IGNORE__", "")) == "":
                    pass  # do not delete token if it's all numbers
                else:
                    word = re.sub("[0-9]", "", word)
            ipa_form = ''
            if word.startswith("__IGNORE__"):
                ipa_form = word.replace("__IGNORE__", "")
                # mark words we couldn't transliterate with an asterisk:

                if mark:
                    if not re.sub("\d*", "", ipa_form) == "":
                        ipa_form += "*"
            else:
                for piece in word.split(" "):
                    marked = False
                    unmarked = piece
                    if piece[0] in ["ˈ", "ˌ"]:
                        marked = True
                        mark = piece[0]
                        unmarked = piece[1:]
                    if unmarked in symbols:
                        if marked:
                            ipa_form += mark + symbols[unmarked]
                        else:
                            ipa_form += symbols[unmarked]

                    else:
                        ipa_form += piece
            swap_list = [["ˈər", "əˈr"], ["ˈie", "iˈe"]]
            for sym in swap_list:
                if not ipa_form.startswith(sym[0]):
                    ipa_form = ipa_form.replace(sym[0], sym[1])
            ipa_word_list.append(ipa_form)
        ipa_list.append(sorted(list(set(ipa_word_list))))
    return ipa_list


def get_top(ipa_list):
    """Returns only the one result for a query. If multiple entries for words are found, only the first is used."""
    return ' '.join([word_list[-1] for word_list in ipa_list])


def get_all(ipa_list):
    """utilizes an algorithm to discover and return all possible combinations of IPA transcriptions"""
    final_size = 1
    for word_list in ipa_list:
        final_size *= len(word_list)
    list_all = ["" for s in range(final_size)]
    for i in range(len(ipa_list)):
        if i == 0:
            swtich_rate = final_size / len(ipa_list[i])
        else:
            swtich_rate /= len(ipa_list[i])
        k = 0
        for j in range(final_size):
            if (j+1) % int(swtich_rate) == 0:
                k += 1
            if k == len(ipa_list[i]):
                k = 0
            list_all[j] = list_all[j] + ipa_list[i][k] + " "
    return sorted([sent[:-1] for sent in list_all])


def ipa_list(words_in, keep_punct=True, stress_marks='both'):
    """Returns a list of all the discovered IPA transcriptions for each word."""
    if type(words_in) == str:
        words = [preserve_punc(w.lower())[0] for w in words_in.split()]
    else:
        words = [preserve_punc(w.lower())[0] for w in words_in]
    cmu = get_cmu([w[1] for w in words])
    ipa = cmu_to_ipa(cmu, stress_marking=stress_marks)
    if keep_punct:
        ipa = _punct_replace_word(words, ipa)
    return ipa


def isin_cmu(word):
    """checks if a word is in the CMU dictionary. Doesn't strip punctuation.
    If given more than one word, returns True only if all words are present."""
    if type(word) == str:
        word = [preprocess(w) for w in word.split()]
    results = fetch_words(word)
    as_set = list(set(t[0] for t in results))
    return len(as_set) == len(set(word))


def get_viseme(phoneme_map, language):

    global VISEMES

    viseme_str = ""

    phoneme_words = phoneme_map.split(" ")
    viseme_words = []

    for w in phoneme_words:
        if "*" not in w:
            viseme_str = ""
            i=0
            while i < len(w):

                if w[i] in [" ", "'"]:
                    viseme_str += w[i]
                else:
                    if i + 1 < len(w):
                        if (w[i] + w[i + 1]) in VISEMES["diphtong"]:
                            viseme_str += VISEMES[language][w[i] + w[i + 1]]
                            i += 1
                        else:
                            viseme_str += VISEMES[language][w[i]]
                    else:
                        viseme_str += VISEMES[language][w[i]]

                i += 1
            viseme_words.append(viseme_str)
        else:
            if "$" in w:
                viseme_words.append(w.replace("*", "").replace("$", "").upper() + "z")
            else:
                viseme_words.append(w.replace("*", "").upper())
    return " ".join(viseme_words)

def get_all_viseme(phoneme_map, language):
    l = []
    for wl in phoneme_map:
        subl = []
        for w in wl:
            subl.append(get_viseme(w))
        l.append(subl)
    return l

def convert(text, retrieve_all=False, keep_punct=True, stress_marks='primary', viseme=False, viseme_language="british", no_stress=True):
    """takes either a string or list of English words and converts them to IPA"""
    ipa = ipa_list(
                   words_in=text,
                   keep_punct=keep_punct,
                   stress_marks=stress_marks
                   )
    
    ans = None
    if no_stress:
        if retrieve_all:
            ans = get_all(ipa)
            for i, l in enumerate(ans, 0):
                for j, w in enumerate(l, 0):
                    ans[i][j] = w.replace("ˈ", "").replace("ˌ", "")
        else:
            ans = get_top(ipa)
            ans = ans.replace("ˈ", "").replace("ˌ", "")
                    
    if viseme:
        if retrieve_all:
            return get_all_viseme(ans, viseme_language)
        return get_viseme(ans, viseme_language)
    else:
        phonemes_words = ans.split(" ")
        print(ans)
        final = []
        for w in phonemes_words:
            if "*" in w:
                if "$" in w:
                    final.append(w.replace("*", "").replace("$", "").upper() + "z")
                else:
                    final.append(w.replace("*", "").upper())
            else:
                final.append(w)
        return " ".join(final)

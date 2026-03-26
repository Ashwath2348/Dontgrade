import re


def count_sentences(text):
    return len(re.findall(r'[.!?]+', text)) or 1


def count_words(text):
    return len(re.findall(r'\b\w+\b', text)) or 1


def count_syllables(word):
    word = word.lower()
    syllables = re.findall(r'[aeiouy]+', word)
    return max(1, len(syllables))


def total_syllables(text):
    return sum(count_syllables(word) for word in re.findall(r'\b\w+\b', text))


def flesch_reading_ease(sentences, words, syllables):
    asl = words / sentences
    asw = syllables / words
    return 206.835 - (1.015 * asl) - (84.6 * asw)


def flesch_kincaid_grade(sentences, words, syllables):
    asl = words / sentences
    asw = syllables / words
    return 0.39 * asl + 11.8 * asw - 15.59


def classify_readability(score):
    if score >= 60:
        return "Easy"
    elif score >= 30:
        return "Medium"
    else:
        return "Hard"

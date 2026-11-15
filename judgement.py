from time import sleep

import sentence_create
import voice_play


def judgement():
    excuse = sentence_create.next_lawyer_excuse()
    prosecutor = sentence_create.next_prosecutor_sentence()
    judge = sentence_create.next_judgment()
    voice_play.speak('裁判を開廷します。', speaker=16)
    voice_play.speak('弁護士', speaker=16)
    voice_play.speak(f'{excuse}', speaker=11)
    voice_play.speak('検察官', speaker=16)
    voice_play.speak(f'{prosecutor}', speaker=9)
    voice_play.speak('裁判官', speaker=16)
    voice_play.speak(f'{judge}', speaker=13)
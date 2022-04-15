import argparse
import ast
import json
import logging
import os
import re
import sqlite3
import unicodedata
from typing import Optional

import requests
from google.protobuf import json_format

import cjedb_pb2

UPSTREAM_DATA_URL = 'https://gamewith-tool.s3-ap-northeast-1.amazonaws.com/uma-musume/male_event_datas.js'
UPSTREAM_DATA_HEADER = '''window.eventDatas['男'] = ['''
UPSTREAM_DATA_FOOTER = '];'

EXCLUDED_EVENT_CHARA_NAMES = {'共通', 'URA', 'アオハル', 'クライマックス'}
LOW_PRIORITY_CHARA_NAMES = {'チーム＜シリウス＞'}

EXCLUDED_EVENT_NAMES = {
    '追加の自主トレ', '夏合宿（2年目）にて', '夏合宿(2年目)にて', '初詣', '新年の抱負',
    'お大事に！', '無茶は厳禁！',
    'レース勝利！(1着)', 'レース入着(2~5着)', 'レース敗北(6着以下)', 'レース勝利！', 'レース入着', 'レース敗北',
    '今度こそ負けない！',
    'あんし〜ん笹針師、参☆上',
    'チーム＜ファースト＞の宣戦布告', 'ついに集まったチームメンバー！',  # Aoharu only
}

EVENT_NAME_SUFFIX_TO_REMOVE = {'（お出かけ2）', '（お出かけ3）', '（Rお出かけ3）'}

PER_CHARA_EXCLUDE_EVENTS = {
    ('夏合宿(3年目)終了', 1007),  # ゴルシ, wrong event name, but no one else has this choice, and the choice does nothing
    ('レース勝利', 1024),  # マヤノ, without exclamation mark at the end. Both this and the normal one appear in gallery
    ('レース入着(2/4/5着)', 1060),  # ナイスネイチャ
    ('天皇賞(秋)の後に・空に手を', 1069),  # サクラチヨノオー, the choices explain their effect quite well.

    # ゴールドシチー
    ('レース勝利！(クラシック10月後半以前1着)', 1040),
    ('レース入着(クラシック10月後半以前2~5着)', 1040),
    ('レース敗北(クラシック10月後半以前6着以下)', 1040),
    ('レース勝利！(クラシック11月前半以降1着)', 1040),
    ('レース入着(クラシック11月前半以降2~5着)', 1040),
    ('レース敗北(クラシック11月前半以降6着以下)', 1040),
    ('レース勝利！(シニア5月前半以降1着)', 1040),
    ('レース入着(シニア5月前半以降2~5着)', 1040),
    ('レース敗北(シニア5月前半以降6着以下)', 1040),
}

PERMITTED_DUPLICATED_EVENTS = {
    # 理事長. One has choices, the other one doesn't. We don't care and just anyway show.
    ('上々の面構えッ！', None): {400001024, 400001037},

    # ダイワスカーレット. One for ☆2 and one for ☆3.
    ('アイツの存在', 1009): {501009115, 501009413},

    # ゴルドシープ. ☆2 vs ☆3, multiplied by one with choice (宝塚二連覇) vs doesn't. Don't care and anyway show.
    ('宝塚記念の後に・キーワード②', 1007): {501007309, 501007310, 501007423, 501007424},

    # ナリタブライアン. One with choices and one doesn't. Don't care and anyway show.
    ('岐', 1016): {501016121, 501016409},

    # フジキセキ
    ('第一幕　スマイル', 1005): {501005113, 501005401},

    # ファインモーション
    ('Who Will Escort Me?', 1022): {501022118, 501022406},

    # メジロアルダン
    ('道、分かたれて', 1071): {501071116, 501071404},

    # ニシノフラワー. 2 consecutive events with the same name. Upstream groups them as a single event. 
    ('夜に咲く想い', 1051): {501051524, 501051525},

    # Aoharu, team name
    ('ついに集まったチームメンバー！', None): {400002204, 400002217, 400002444},
}

DUPLICATED_EVENTS_DEDUPE = {
    # 1061 キングヘイロー, 1019 アグネスデジタル
    ('一流の条件', 1061): ({501019116, 501061704}, [501061704]),

    # 1021 タマモクロス, 1024 マヤノトップガン
    # For マヤノ, this behaves the same to the normal one and is excluded above by PER_CHARA_EXCLUDE_EVENTS
    # For タマ, this is the special one during バ群を怖がる期間
    ('レース勝利', 1021): ({501021734, 501024724}, [501021734]),
}

KNOWN_OVERRIDES = {
    ('秋川理事長のご褒美！', None): 'ついに集まったチームメンバー！',  # Aoharu. Manually show the outcome during where the choice happens

    ('女帝vs."帝王"', 1003): '“女帝”vs.“帝王”',
    ('支えあいの秘訣', 1004): '支え合いの秘訣',
    ('えっアタシのバイト…やばすぎ？', 1007): 'えっアタシのバイト……ヤバすぎ？',
    ('挑め、”宿命”', 1008): '挑め、“宿命”',
    ('楽しめ！一番！', 1009): '楽しめ！　1番！',
    ('女帝と"帝王"', 1018): '“女帝”と“帝王”',
    ('女帝と"皇帝"', 1018): '“女帝”と“皇帝”',
    ('ラスボスはスペ', 1052): 'ラスボスはスぺ',  # ペ in master.mdb is ひらがな...
    ('覇王として', 1015): '“覇王”として',
    ('麗姿、瞳に焼き付いて', 1018): '麗姿、瞳に焼きついて',
    ('すべてはーーーのため', 1038): 'すべては――のため',
    ('You’re My Sunshine☆', 1024): 'You\'re My Sunshine☆',
    ('With My Whole Heart!', 1024): 'With My Whole Heart！',
    ('甦れ！ゴルシ印のソース焼きそば！', 1007): '甦れ！　ゴルシ印のソース焼きそば！',
    ('08:36/朝寝坊、やばっ', 1040): '08:36／朝寝坊、やばっ',
    ('ヒシアマ姐さん奮闘記～問題児編～', 1012): 'ヒシアマ姐さん奮闘記　～問題児編～',
    ('シチースポットを目指して', 1029): '“シチースポット”を目指して',
    ('信仰心と親切心が交わる時ーー', 1056): '信仰心と親切心が交わる時――',
    ('13:12/昼休み、気合い入れなきゃ', 1040): '13:12／昼休み、気合い入れなきゃ',
    ('ヒシアマ姐さん奮闘記～追い込み編～', 1012): 'ヒシアマ姐さん奮闘記　～追い込み編～',
    ('オゥ！トゥナイト・パーティー☆', 1010): 'オゥ！　トゥナイト・パーティー☆',
    ('皇帝の激励', 1017): '“皇帝”の激励',
    ('#lol #Party! #2nd', 1065): '#lol #Party!! #2nd',
    ('検証〜ネコ語は実在するのか？', 1020): '検証～ネコ語は実在するのか？',
    ('＠DREAM_MAKER', 1005): '@DREAM_MAKER',
    ('人生最大の幸運とは', 1005): '人生最大の幸福とは',
    ('What a wonderful stage!', 1005): 'What a wonderful stage！',
    ('あんしんかばん', 1058): 'あんしんカバン',
    ('奏でようWINNING!', 1002): '奏でようWINNING！',
    ('推しえて、デジタル先生！', 1019): '“推し”えて、デジタル先生！',
    ('あなたの背中を"推し"たくて……', 1019): 'あなたの背中を“推し”たくて……',
    ('推しみない愛を推しに！', 1019): '“推し”みない愛を推しに！',
    ('Search  or Mommy', 1045): 'Search or Mommy',
    ('シチーガールの今の気分♪', 1040): '“シチーガール”の今の気分♪',
    ('勝利の味ってヤツ！', 1048): '勝利の味ってヤツ!',
    ('殿下と映画鑑賞会', 1022): '殿下と映画観賞会',
    ('言葉+……', 1033): '言葉＋……',
    ('未来が分かる魔法かも？', 1074): '未来がわかる魔法かも？',
    ('支えられて、見守られて', 1074): '支えらえて、見守られて', # ... lol
    ('『全力』&『普通』ダイエット！', None): '『全力』＆『普通』ダイエット！',
}


def fetch_gw_upstream():
    r = requests.get(UPSTREAM_DATA_URL)
    r.encoding = 'utf-8'
    c = r.text
    c = c[c.find(UPSTREAM_DATA_HEADER) + len(UPSTREAM_DATA_HEADER) + 1:c.find(UPSTREAM_DATA_FOOTER)]
    return ast.literal_eval('[' + c + ']')  # A bad hack because Python happens to accept this :(


def open_db(path: str) -> sqlite3.Cursor:
    connection = sqlite3.connect(path)
    return connection.cursor()


def read_chara_names(cursor: sqlite3.Cursor) -> dict[str, int]:
    cursor.execute("""SELECT "index", text FROM text_data
                      WHERE category=170""")  # Not 6 because of '桐生院葵'
    return {row[1]: row[0] for row in cursor.fetchall()}


def try_match_event(cursor: sqlite3.Cursor, event_name: str, chara_id: Optional[int], unused_known_overrides: set) \
        -> list[int]:
    original_event_name = event_name
     # Currently no events use these replaced chars
    event_name = event_name.replace('･', '・').replace('~', '～').replace('(', '（').replace(')', '）')
    for suffix in EVENT_NAME_SUFFIX_TO_REMOVE:
        event_name = event_name.removesuffix(suffix)

    t = (event_name, chara_id)
    if t in KNOWN_OVERRIDES:
        unused_known_overrides.discard(t)
        event_name = KNOWN_OVERRIDES[t]
        t = (event_name, chara_id)

    cursor.execute("""SELECT "index" FROM text_data
                      WHERE category=181 AND text=?""", [event_name])
    possible_story_ids = [row[0] for row in cursor.fetchall()]

    if len(possible_story_ids) == 0:
        cursor.execute("""SELECT "index", text FROM text_data
                          WHERE category=181 AND text LIKE ?""", ['%' + event_name + '%'])
        rows = cursor.fetchall()
        if len(rows) == 1:
            row = rows[0]
            if str(row[0]).startswith('50%d' % chara_id) or str(row[0]).startswith('80%d' % chara_id):
                # Chara ID matches, just INFO.
                logging.info(
                    "Fuzzily mapped %s for chara %s to %s %s" % (original_event_name, chara_id, row[0], row[1]))
            else:
                logging.warning(
                    "Fuzzily mapped %s for chara %s to %s %s" % (original_event_name, chara_id, row[0], row[1]))
            return [row[0]]

        logging.warning("Unknown event %s for chara %s" % (original_event_name, chara_id))
        return []

    if len(possible_story_ids) == 1:
        return possible_story_ids

    if event_name == 'ダンスレッスン':
        # Just special case this...
        story_id = int('50%d506' % chara_id)
        if story_id in possible_story_ids:
            return [story_id]

    if t in PERMITTED_DUPLICATED_EVENTS:
        if set(possible_story_ids) == PERMITTED_DUPLICATED_EVENTS[t]:
            return possible_story_ids

    if t in DUPLICATED_EVENTS_DEDUPE:
        if set(possible_story_ids) == DUPLICATED_EVENTS_DEDUPE[t][0]:
            return DUPLICATED_EVENTS_DEDUPE[t][1]

    logging.warning("More than 1 event for event_name %s for char %s" % (original_event_name, chara_id))
    return []


def match_events(cursor: sqlite3.Cursor, gw_data):
    chara_names = read_chara_names(cursor)

    unused_known_overrides = set(KNOWN_OVERRIDES.keys())
    result = {}
    low_priority_result = {}

    for row in gw_data:
        event_name = unicodedata.normalize('NFC', row['e'])

        event_type = row['c']  # c: chara, s: support card, m: scenario?
        if event_type not in {'c', 's', 'm'}:
            logging.error('Detected unknown event_type: %s' % row)

        event_chara_name = re.sub(r'\(.+\)', "", row['n'])  # remove things like `(新衣装)`
        m = re.search('[\u30A0-\u30FF]+', event_chara_name)
        if event_chara_name not in EXCLUDED_EVENT_CHARA_NAMES and event_chara_name not in LOW_PRIORITY_CHARA_NAMES:
            if m:
                # If it contains some Katakana, just remove all non Katakana chars
                event_chara_name = m[0]
            if event_chara_name not in chara_names:
                logging.warning('Detected unknown event_chara: %s' % row)
        chara_id = chara_names.get(event_chara_name)

        if event_name in EXCLUDED_EVENT_NAMES or (event_name, chara_id) in PER_CHARA_EXCLUDE_EVENTS:
            continue

        to_update = low_priority_result if event_chara_name in LOW_PRIORITY_CHARA_NAMES else result

        story_ids = try_match_event(cursor, event_name, chara_id, unused_known_overrides)
        for story_id in story_ids:
            if story_id in to_update:
                # Because upstream uses separate entries for support cards R vs SR vs SSR, or different 勝負服 of the same chara.
                # For now there is no case where the choices are different than each other, so just ignore.
                pass
            to_update[story_id] = row

    if len(unused_known_overrides) > 0:
        logging.warning('Unused KNOWN_OVERRIDES: %s', unused_known_overrides)

    return low_priority_result | result


text_formatter = lambda text: text.replace('[br]', '\n').replace('<hr>', '\n')


def convert_to_proto(events: dict, include_name: bool) -> cjedb_pb2.Database:
    db = cjedb_pb2.Database()
    for k, v in sorted(events.items()):
        e = cjedb_pb2.Event()
        e.story_id = k
        for choice in v['choices']:
            c = cjedb_pb2.Event.Choice()
            c.title = choice['n']
            c.text = text_formatter(choice['t'])
            e.choices.append(c)
        if include_name:
            e.story_name = v['e']
        db.events.append(e)
    return db


def main():
    logging.basicConfig(level=os.environ.get('LOGLEVEL', 'WARNING').upper())

    parser = argparse.ArgumentParser()
    parser.add_argument("--db_path", default="master.mdb")
    parser.add_argument("--output", default="cjedb.json")
    parser.add_argument("--include_name", action='store_true')
    args = parser.parse_args()

    gw_data = fetch_gw_upstream()
    cursor = open_db(args.db_path)

    events = match_events(cursor, gw_data)
    db = convert_to_proto(events, args.include_name)

    with open(args.output, 'w') as f:
        json.dump(json_format.MessageToDict(db), f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()

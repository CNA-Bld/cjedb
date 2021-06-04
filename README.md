# cjedb

cjedb provides additional data to [EXNOA-CarrotJuicer](https://github.com/CNA-Bld/EXNOA-CarrotJuicer) for additional
functionalities.

If you are a user of EXNOA-CarrotJuicer, please just
put [cjedb.json](https://github.com/CNA-Bld/cjedb/raw/master/cjedb.json) into `umamusume.exe`'s directory.

## Schema

Schema is defined by [cjedb.proto](cjedb.proto). Run `protoc --python_out=. *.proto` to update the generated Python
code.

Although schema is defined as a protobuf, currently proto3 JSON is used as the data exchange format.

## Generate `cjedb.json`

Run `generator.py --db_path <path_to_master.mdb> --output <path_to_cjedb.json>`. Both options are optional, and they
default to the files in the working directory.

The only pip dependencies are `requests` and `protobuf`.

## Components

### `events`

This contains data for events that behave differently based on user choices.

Data comes from [GameWith](https://gamewith.jp/uma-musume/article/show/259587). The generator will automatically fetch a
live version when it runs.

It attempts to do fuzzy matching whenever possible (with some terrible hacks), and when that doesn't work it will print
a warning message. Known exceptions:

* General events that are the same across all characters are just ignored (like 追加の自主トレ). Please just recite them with
  brain. A full list is in `EXCLUDED_EVENT_NAMES`.
* General events that are different for characters (currently only ダンスレッスン) are hardcoded manually with some safety
  checks against `master.mdb`.
* Some character specific events are also excluded. See `PER_CHARA_EXCLUDE_EVENTS`.
* Some events have several copies. See `PERMITTED_DUPLICATED_EVENTS` for details.
* Finally, `KNOWN_OVERRIDES` is the list of events where the name cannot be fuzzy matched, so they got manually mapped.

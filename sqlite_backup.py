import sqlite3
import r6_db
import json
import datetime
from datetime import timezone, timedelta
import pathlib


def profile_json_for_excel(json_path):
    with open(json_path, 'r', encoding="utf8") as f:
        data = json.load(f)
    all_result = {}
    result = all_result['profile'] = []
    for d in data:
        result.append(d)
    output_path = pathlib.Path(json_path)
    output_path = output_path.parent / (output_path.stem + '_output.json')
    with open(output_path, 'w') as fw:
        json.dump(all_result, fw, indent=4)


if __name__ == '__main__':
    profile_json_for_excel('profile.json')

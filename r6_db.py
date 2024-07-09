import sqlite3
import enum
import datetime
import pprint
import random
import itertools


class BaseDatabase:
    def __init__(self, db_path, table_name='setting'):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        self.c = self.conn.cursor()
        self.TABLE_NAME = table_name

    @staticmethod
    def dict_factory(cursor, row):
        # use self.conn.row_factory = self.dict_factory
        # when needing the dict support
        d = {}
        for idx, col in enumerate(cursor.description):
            if d.get(col[0]) is None:
                d[col[0]] = row[idx]
        return d

    def execute_rowcount(self, cmd, vals):
        res = self.c.execute(cmd, vals)
        self.conn.commit()
        return res.rowcount


class SettingDatabase(BaseDatabase):
    def __init__(self, db_path, guild_id=0, table_name='setting'):
        super().__init__(db_path, table_name)
        self.guild_id = guild_id
        self.c.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME}(
                guild_id INTEGER,
                type TEXT,
                name TEXT,
                value TEXT,
                UNIQUE(guild_id, type, name)
            )""")
        self.conn.commit()

    def save(self, type_name, name, value, guild_id=None):
        guild_id = guild_id or self.guild_id
        value = str(value)
        cur = self.c.execute(f"""
            INSERT OR REPLACE INTO {self.TABLE_NAME}
            VALUES (?, ?, ?, ?) 
        """, (guild_id, str(type_name), str(name), value))
        self.conn.commit()
        return cur.rowcount

    def get(self, type_name, name, guild_id=None):
        guild_id = guild_id or self.guild_id
        self.c.execute(f"""
            SELECT value FROM {self.TABLE_NAME} 
            WHERE guild_id = ? AND type = ? AND name = ?
        """, (guild_id, str(type_name), str(name)))
        res = self.c.fetchone()
        return res[0] if res else None

    def getint(self, type_name, name, guild_id=None):
        res = self.get(type_name, name, guild_id)
        return None if res is None else int(res)

    def delete(self, type_name, name, guild_id=None):
        cur = self.c.execute(f"""
            DELETE FROM {self.TABLE_NAME}
            WHERE guild_id = ? AND type = ? AND name = ?
        """, (guild_id, str(type_name), str(name)))
        self.conn.commit()
        return cur.rowcount

    def get_all_guild(self, type_name, name):
        self.c.execute(f"""
                    SELECT guild_id, value FROM {self.TABLE_NAME} 
                    WHERE type = ? AND name = ?
                """, (str(type_name), str(name)))
        res = self.c.fetchall()
        return res


class GameStateTypes(str, enum.Enum):
    WAITING = 'WAITING'
    PLAYING = 'PLAYING'
    FINISHED = 'FINISHED'
    ASSIGNING = 'ASSIGNING'


class GameDatabase(BaseDatabase):
    def __init__(self, db_path, guild_id=0, table_name='game',
                 game_member_table_name='game_member', game_attr_table_name='game_attr'):
        super().__init__(db_path, table_name)
        self.conn.row_factory = self.dict_factory
        self.c = self.conn.cursor()

        self.game_member_table_name = game_member_table_name
        self.game_attr_table_name = game_attr_table_name
        self.guild_id = guild_id
        self.c.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME}(
                guild_id INTEGER,
                game_id INTEGER,
                map TEXT,
                region TEXT,
                state TEXT,
                winner INTEGER,

                created_timestamp TIMESTAMP,
                UNIQUE(guild_id, game_id)
            )""")
        self.c.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.game_member_table_name}(
                guild_id INTEGER,
                game_id INTEGER,
                member_id INTEGER,
                team INTEGER,
                UNIQUE(guild_id, game_id, member_id)
            )""")
        self.c.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.game_attr_table_name}(
                        guild_id INTEGER,
                        game_id INTEGER,
                        attr_name TEXT,
                        attr_value TEXT,
                        UNIQUE(guild_id, game_id, attr_name)
                    )""")

        self.conn.commit()

        cursor = self.c.execute(f'SELECT * FROM {self.game_member_table_name}')
        names = [description[0] for description in cursor.description]
        _ = cursor.fetchall()
        print(names)
        if 'add_time' not in names:
            print('add_time added')
            self.c.execute(f"""ALTER TABLE {self.game_member_table_name}
                               ADD COLUMN add_time TIMESTAMP""")
            self.conn.commit()

        self.map_list = ["Oregon", "Clubhouse", "Kafe Dostoyevksy", "Consulate", "Chalet", "Bank", "Nighthaven Labs", "Border", "Skyscraper"]

    def new_game(self, map_name=None, region=None, timestamp=None, guild_id=None):
        guild_id = guild_id or self.guild_id
        self.c.execute(f"""
            SELECT MAX(game_id) FROM {self.TABLE_NAME}
            WHERE guild_id = ?
        """, (guild_id,))
        new_game_id = self.c.fetchone()
        new_game_id = (new_game_id['MAX(game_id)'] + 1) if new_game_id and new_game_id['MAX(game_id)'] else 1
        timestamp = timestamp or datetime.datetime.now()
        cur = self.c.execute(f"""
            INSERT OR REPLACE INTO {self.TABLE_NAME}
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (guild_id, new_game_id, map_name, region, GameStateTypes.WAITING, None, timestamp))
        self.conn.commit()
        return new_game_id

    def add_member_to_game(self, game_id, member_id, team, guild_id=None, add_time=None):
        guild_id = guild_id or self.guild_id
        add_time = add_time or datetime.datetime.now()
        cur = self.c.execute(f"""
            INSERT OR REPLACE INTO {self.game_member_table_name} 
            VALUES (?, ?, ?, ?, ?) 
        """, (guild_id, game_id, member_id, team, add_time))
        self.conn.commit()
        return cur.rowcount

    def remove_member_from_game(self, game_id, member_id, guild_id=None):
        guild_id = guild_id or self.guild_id
        cur = self.c.execute(f"""
            DELETE FROM {self.game_member_table_name}
            WHERE guild_id = ? AND game_id = ? AND member_id = ?
        """, (guild_id, game_id, member_id))
        self.conn.commit()
        return cur.rowcount

    def get_game_by_id(self, game_id, guild_id=None):
        guild_id = guild_id or self.guild_id
        cur = self.c.execute(f"""
                    SELECT * FROM {self.TABLE_NAME}
                    WHERE guild_id = ? AND game_id = ?
                """, (guild_id, game_id))
        return self.c.fetchone()

    def get_game_members_by_id(self, game_id, guild_id=None, team=None):
        guild_id = guild_id or self.guild_id
        if team is None:
            team_cmp = ''
            args = (guild_id, game_id)
        else:
            team_cmp = 'AND team = ?'
            args = (guild_id, game_id, team)
        cur = self.c.execute(f"""
                    SELECT * FROM {self.game_member_table_name}
                    WHERE guild_id = ? AND game_id = ? {team_cmp}
                """, args)
        return self.c.fetchall()

    def get_game_info(self, game_id, guild_id=None):
        guild_id = guild_id or self.guild_id
        return self.get_game_by_id(game_id, guild_id), self.get_game_members_by_id(game_id, guild_id=guild_id)

    @staticmethod
    def sql_in_list(name, data, add_and=True):
        if not data:
            return '', []
        else:
            if type(data) is not list:
                data = [data]
            if add_and:
                return f"AND {name} IN ({','.join(['?'] * len(data))})", data
            else:
                return f"{name} IN ({','.join(['?'] * len(data))})", data

    def get_games(self, states=None, regions=None, guild_id=None):
        guild_id = guild_id or self.guild_id

        states_cmp, states = self.sql_in_list('state', states)
        regions_cmp, regions = self.sql_in_list('region', regions)

        self.c.execute(f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE {self.TABLE_NAME}.guild_id = ? {regions_cmp} {states_cmp}""",
                       (guild_id, *regions, *states))
        res = self.c.fetchall()
        return res

    def get_members(self, member_ids=None, states=None, regions=None, guild_id=None):
        guild_id = guild_id or self.guild_id

        member_ids_cmp, member_ids = self.sql_in_list('member_id', member_ids)
        states_cmp, states = self.sql_in_list('state', states)
        regions_cmp, regions = self.sql_in_list('region', regions)

        self.c.execute(f"""
            SELECT * FROM {self.TABLE_NAME}
            INNER JOIN {self.game_member_table_name} 
            ON {self.game_member_table_name}.guild_id = {self.TABLE_NAME}.guild_id AND
               {self.game_member_table_name}.game_id = {self.TABLE_NAME}.game_id 
            WHERE {self.TABLE_NAME}.guild_id = ? {member_ids_cmp} {regions_cmp} {states_cmp}""",
                       (guild_id, *member_ids, *regions, *states))
        res = self.c.fetchall()
        return res

    def get_game_teams(self, guild_id, game_id):
        teams = [[], [], []]
        players = self.get_game_members_by_id(game_id, guild_id)
        for p in players:
            team_id = p['team']
            if team_id is None:
                # to-be-assign-team
                teams[2].append(p)
            else:
                teams[team_id - 1].append(p)
        if len(teams[2]) > 0:
            teams[2] = sorted(teams[2], key=lambda p: p['member_id'])
        return teams

    def get_member_waiting_game(self, member_id, guild_id=None):
        guild_id = guild_id or self.guild_id
        return self.get_members(member_id, states=GameStateTypes.WAITING, guild_id=guild_id)

    def set_members_team(self, game_id, players, team, guild_id=None):
        guild_id = guild_id or self.guild_id
        for player in players:
            member_id = player['member_id']
            self.c.execute(f"""
                UPDATE {self.game_member_table_name}
                SET team = ?
                WHERE guild_id = ? AND game_id = ? AND member_id = ? 
            """, (team, guild_id, game_id, member_id))
        self.conn.commit()

    def random_assign_team(self, game_id, players, profile_db, guild_id=None):
        # pass players as argument here is for efficiency,
        # player_profiles is profile dicts.
        guild_id = guild_id or self.guild_id

        # This is the part need to be revised for balance

        player_profiles = []
        score_sum = 0
        score_profiles = {}
        scores = []
        for player in players:
            profile = profile_db.get_profile(player['member_id'], guild_id=guild_id)
            player_profiles.append(profile)
            score = profile['score']
            score_sum += score
            scores.append(score)
            if score_profiles.get(score) is None:
                score_profiles[score] = [profile]
            else:
                score_profiles[score].append(profile)
        half_score_sum = score_sum // 2
        # player_profiles = sorted(player_profiles, key=lambda p: p['score'], reverse=True)
        # teams = ([player_profiles[idx] for idx in range(0, 10, 2)],
        #          [player_profiles[idx] for idx in range(1, 10, 2)])
        all_combinations = list(itertools.combinations(scores, 5))
        combinations_dist = list(map(lambda li: abs(sum(li) - half_score_sum), all_combinations))
        index_min = min(range(len(combinations_dist)), key=combinations_dist.__getitem__)
        min_comb = list(all_combinations[index_min])
        teams = ([], [])
        for score in min_comb:
            teams[0].append(score_profiles[score].pop())
        for k, v in score_profiles.items():
            for profile in v:
                teams[1].append(profile)

        self.set_members_team(game_id, teams[0], 1, guild_id)
        self.set_members_team(game_id, teams[1], 2, guild_id)
        return teams

    def set_game_state(self, game_id, state, guild_id=None):
        guild_id = guild_id or self.guild_id
        cur = self.c.execute(f"""
                    UPDATE {self.TABLE_NAME}
                    SET state = ?
                    WHERE guild_id = ? AND game_id = ?
                """, (state, guild_id, game_id))
        self.conn.commit()
        return cur.rowcount

    def set_game_map(self, game_id, map_name, guild_id=None):
        guild_id = guild_id or self.guild_id
        cur = self.c.execute(f"""
                            UPDATE {self.TABLE_NAME}
                            SET map = ?
                            WHERE guild_id = ? AND game_id = ?
                        """, (map_name, guild_id, game_id))
        self.conn.commit()
        return cur.rowcount

    def start_game(self, game_id, pdb, guild_id=None):
        # ProfileDatabase need to be passed in.
        # Due to the balance mechanism, and this db has no score data,

        guild_id = guild_id or self.guild_id
        map_name = random.choice(self.map_list)
        self.set_game_map(game_id, map_name, guild_id)
        self.set_game_state(game_id, GameStateTypes.PLAYING, guild_id)
        game_info, players = self.get_game_info(game_id, guild_id)
        teams = self.random_assign_team(game_id, players, pdb, guild_id)
        return teams

    def start_assign_game(self, guild_id, game_id, pdb):
        map_name = random.choice(self.map_list)
        self.set_game_map(game_id, map_name, guild_id)
        self.set_game_state(game_id, GameStateTypes.ASSIGNING, guild_id)
        game_info, players = self.get_game_info(game_id, guild_id)
        player_scores = []
        for player in players:
            profile = pdb.get_profile(player['member_id'], guild_id=guild_id)
            score = profile['score'] if profile is not None else -1
            player_scores.append((player, score))
        # 分數從高到低排序
        player_scores = sorted(player_scores, key=lambda item: -item[1])
        # 取前四隨機打亂後合併
        top_four = player_scores[:4]
        random.shuffle(top_four)
        player_scores = top_four + player_scores[4:]

        # 隨機打亂順序
        # random.shuffle(player_scores)
        teams = [p[0] for p in player_scores]
        teams = ([teams[0]], [teams[1]], teams[2:])
        self.set_members_team(game_id, teams[0], 1, guild_id)
        self.set_members_team(game_id, teams[1], 2, guild_id)
        return teams

    def finish_game(self, game_id, guild_id=None):
        guild_id = guild_id or self.guild_id
        self.set_game_state(game_id, GameStateTypes.FINISHED, guild_id)

    def remove_game(self, game_id, guild_id=None):
        guild_id = guild_id or self.guild_id
        rowcount = 0
        cur = self.c.execute(f"""
            DELETE FROM {self.TABLE_NAME}
            WHERE guild_id = ? AND game_id = ?
        """, (guild_id, game_id))
        rowcount += cur.rowcount
        self.c.execute(f"""
            SELECT * FROM {self.game_member_table_name}
            WHERE guild_id = ? AND game_id = ?
        """, (guild_id, game_id))
        removed_members = self.c.fetchall()
        self.c.execute(f"""
            DELETE FROM {self.game_member_table_name}
            WHERE guild_id = ? AND game_id = ?
        """, (guild_id, game_id))
        rowcount += cur.rowcount
        self.conn.commit()
        return removed_members

    def set_game_attr(self, guild_id, game_id, attr_name, attr_value):
        cur = self.c.execute(f"""
            INSERT OR REPLACE INTO {self.game_attr_table_name}(guild_id, game_id, attr_name, attr_value)
            VALUES(?,?,?,?)
        """, (guild_id, game_id, attr_name, attr_value))
        self.conn.commit()
        return cur.rowcount

    def delete_game_attr(self, guild_id, game_id, attr_name):
        cur = self.c.execute(f"""
        DELETE FROM {self.game_attr_table_name}
        WHERE guild_id = ? AND game_id = ? AND attr_name = ?
        """, (guild_id, game_id, attr_name))
        self.conn.commit()
        return cur.rowcount

    def get_game_attr(self, guild_id, game_id, attr_name):
        self.c.execute(f"""
                    SELECT * FROM {self.game_attr_table_name}
                    WHERE guild_id=? AND game_id=? AND attr_name=?
                """, (guild_id, game_id, attr_name))
        result = self.c.fetchone()
        return result['attr_value'] if result else None

    def get_game_attr_int(self, guild_id, game_id, attr_name):
        res = self.get_game_attr(guild_id, game_id, attr_name)
        res = int(res) if res is not None else None
        return res

    def get_game_attrs(self, guild_id, game_id):
        self.c.execute(f"""
            SELECT * FROM {self.game_attr_table_name}
            WHERE guild_id=? AND game_id=?
        """, (guild_id, game_id))
        result = self.c.fetchall()
        result_dict = {attr['attr_name']: attr['attr_value'] for attr in result}
        return result_dict

    def testing_add_9_game(self, region=None, guild_id=None):
        game_id = self.new_game(region=region, guild_id=guild_id)
        for i in range(9):
            self.add_member_to_game(game_id, i, None, guild_id)


class ProfileDatabase(BaseDatabase):
    def __init__(self, db_path, guild_id=0, table_name='profile'):
        super().__init__(db_path, table_name)
        self.conn.row_factory = self.dict_factory
        self.c = self.conn.cursor()

        self.guild_id = guild_id
        self.c.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME}(
                guild_id INTEGER,
                member_id INTEGER,
                name TEXT,
                register_timestamp TIMESTAMP,

                score INTEGER,
                lose INTEGER,
                win INTEGER,
                game INTEGER,
                winning_streak INTEGER,
                
                UNIQUE(guild_id, member_id)
            )""")
        self.conn.commit()

        self.init_profile_season_data = {
            'score': 1200,
            'game': 0,
            'lose': 0,
            'win': 0,
            'winning_streak': 0
        }

    def add_profile(self, member_id, name, register_timestamp=None, guild_id=None):
        guild_id = guild_id or self.guild_id
        register_timestamp = register_timestamp or datetime.datetime.now()
        cur = self.c.execute(f"""
            INSERT OR REPLACE INTO {self.TABLE_NAME}
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (guild_id, member_id, name, register_timestamp, 0, 0, 0, 0, 0))
        self.conn.commit()
        return cur.rowcount

    def get_profile(self, member_id, guild_id=None):
        guild_id = guild_id or self.guild_id
        self.c.execute(f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE guild_id = ? AND member_id = ?
        """, (guild_id, member_id))
        return self.c.fetchone()

    def edit_profile(self, member_id, profile, guild_id=None):
        """
            profile is {KEY:NEW_VALUE}, not necessary to have full content of a member.
        """
        guild_id = guild_id or self.guild_id
        rowcount = 0
        for k, v in profile.items():
            cur = self.c.execute(f"""
                UPDATE {self.TABLE_NAME}
                SET {k} = ?
                WHERE guild_id = ? AND member_id = ?
            """, (v, guild_id, member_id))
            rowcount += cur.rowcount
        self.conn.commit()
        return rowcount

    def edit_all_profile(self, profile, guild_id=None):
        guild_id = guild_id or self.guild_id
        rowcount = 0
        for k, v in profile.items():
            cur = self.c.execute(f"""
                        UPDATE {self.TABLE_NAME}
                        SET {k} = ?
                        WHERE guild_id = ?
                    """, (v, guild_id))
            rowcount += cur.rowcount
        self.conn.commit()
        return rowcount

    def edit_name(self, member_id, new_name, guild_id=None, check_duplicate=True):
        guild_id = guild_id or self.guild_id
        if check_duplicate and len(self.get_members_by_name(new_name)) > 0:
            # duplicate found
            return None
        cur = self.c.execute(f"""
            UPDATE {self.TABLE_NAME}
            SET name = ?
            WHERE guild_id = ? AND member_id = ?
        """, (new_name, guild_id, member_id))
        self.conn.commit()
        return cur.rowcount

    def get_members_by_name(self, name, guild_id=None):
        guild_id = guild_id or self.guild_id
        self.c.execute(f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE guild_id = ? AND name = ?
        """, (guild_id, name))
        return self.c.fetchall()

    def get_members(self, guild_id=None):
        guild_id = guild_id or self.guild_id
        self.c.execute(f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE guild_id = ?
        """, (guild_id,))
        return self.c.fetchall()

    def reset_season_data(self, member_id, guild_id=None):
        guild_id = guild_id or self.guild_id
        res = self.edit_profile(member_id, self.init_profile_season_data, guild_id)
        return res

    def reset_all_season_data(self, guild_id=None):
        guild_id = guild_id or self.guild_id
        res = self.edit_all_profile(self.init_profile_season_data, guild_id)
        return res


if __name__ == '__main__':
    # _db_path = ':memory:'
    _db_path = './bot.db'
    # db = SettingDatabase('setting.db', 111)
    guid = 99999
    db = SettingDatabase(_db_path, 111)
    db.save('role', 'Queue', 2222)
    db.save('role', 'Admins', 3333)
    print(db.get('role', 'Queue'))
    gdb = GameDatabase(_db_path, 111)
    pdb = ProfileDatabase(_db_path, 111)
    maps = gdb.map_list
    invite_role_id = 5678
    for i in range(1, 16):
        mid = i * 1
        pdb.add_profile(mid, str(f'name{i:02n}'), guild_id=guid)
        pdb.edit_profile(mid, {'score': 1200 + random.randint(-100, 100)}, guild_id=guid)
        print(pdb.get_profile(mid, guild_id=guid))
    for _map in maps[:1]:
        for i in range(1, 16):
            mid = i * 1
            _region = 'Taiwan'
            if 8 <= i <= 12:
                _region = 'Hong Kong'
            member_waiting_playing_games = gdb.get_members(mid, states=[GameStateTypes.WAITING,
                                                                        GameStateTypes.PLAYING],
                                                           guild_id=guid)
            if len(member_waiting_playing_games) > 0:
                continue

            waiting_games = gdb.get_members(states=GameStateTypes.WAITING, regions=_region, guild_id=guid)
            if waiting_games:
                gid = waiting_games[0]['game_id']
            else:
                gid = gdb.new_game(_map, _region, guild_id=guid)
                # gdb.set_game_attr(gid, 'invite_role_restrict', invite_role_id, guild_id)
                # print(gdb.get_game_attrs(gid, guild_id))
            gdb.add_member_to_game(gid, mid, None, guid)

            game, game_members = gdb.get_game_info(gid, guild_id=guid)
            if len(game_members) >= 10:
                print('game started')
                teams = gdb.start_game(gid, pdb, guild_id=guid)
                game_info, players = gdb.get_game_info(gid, guid)
                print('---info---')
                print(len(teams[0]), len(teams[1]))
                s_sum = 0
                for i in teams[0]:
                    print(i['member_id'], i['score'])
                    s_sum += i['score']
                print('score sum:', s_sum)
                s_sum = 0
                print('team2')
                for i in teams[1]:
                    print(i['member_id'], i['score'])
                    s_sum += i['score']
                print('score sum:', s_sum)
                print(game_info)
                print(players)
    # db.conn.close()
    # gdb.conn.close()
    # pdb.conn.close()
    # print(gdb.get_member_waiting_game(100))
    #
    # for g in gdb.get_members():
    #     print(g)

    # members = pdb.get_members()
    # members = sorted(members, key=lambda item: item['score'], reverse=True)
    # for m in members:
    #     print(m)

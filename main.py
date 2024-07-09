import discord
from discord.ext import commands
import requests
import json
import asyncio
import aiofiles
import random
import discord_slash
from discord_slash import SlashCommand, SlashCommandOptionType
# import pygsheets
# import pandas as pd

from discord_slash.utils.manage_commands import create_choice, create_option

import r6_db
from r6_db import GameStateTypes

from datetime import datetime, timezone, timedelta
import math
import schedule
import traceback
import os.path
import logging

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='-', intents=intents)
bot.remove_command("help")
slash = SlashCommand(bot, sync_commands=True)
lock = asyncio.Lock()

# manager_role_memtion = "<@&954690762170322944>"
log_channel_id = 1110848713917743124

bot.ticket_configs = {}
with open("TOKEN.txt", "r") as fr:
    TOKEN = fr.read()

# # API金鑰
# gc = pygsheets.authorize(service_file="API.json")

# # 表格
# register_list = gc.open_by_url(
#   'https://docs.google.com/spreadsheets/d/1OYnAqLF1Laq4dfxac5FqX80kSmw9RX4BYtepuGQUu_I/edit?usp=sharing'
# )

# register_fill = register_list[0]

db_path = 'bot.db'
setting_db = r6_db.SettingDatabase(db_path)
profile_db = r6_db.ProfileDatabase(db_path)
game_db = r6_db.GameDatabase(db_path)

admin_lock = True
if os.path.exists('./admin_lock_false'):
    admin_lock = False
print('admin lock =', admin_lock)

map_list = ["Oregon", "Clubhouse", "Kafe Dostoyevksy", "Consulate", "Chalet", "Bank", "Nighthaven Labs", "Border", "Skyscraper"]
invite_captain_name = 'Invite-Captain'
invite_random_name = 'Invite-Random'
region_names = [
    'Random',
    'Captain',
#     '快速',
    invite_captain_name,
    invite_random_name,
]

region_name_alias = {
    'Random': ['random', 'r', 'R'],
    'Captain': ['captain', 'c', 'R'],
#     '快速': ['quick'],
    'Invite-Captain': ['invite-captain', 'ic', 'IC', 'iC', 'Ic'],
    'Invite-Random': ['invite-random', 'ir', 'IR', 'iR', 'Ir'],
}
valid_role_types = ["Register", "Queue", "Admins", "Raid", "Invite"]
valid_channel_types = ["Announcement", "Results", "Commands", "Channels", "Invite_Announcement", "Invite_Results", "Invite_Commands"]
valid_setting_types = ["Queuing time limit"]
team_name_id = {
    "Team 1": 1,
    "Team 2": 2,
}
COLOR_INFO = 0x77bb41
COLOR_WARNING = 0xff2600


def json_load(path):
    with open(path, 'r', encoding="big5") as f:
        return json.load(f)


def json_dump(path, obj):
    with open(path, "w+", encoding="big5") as f:
        json.dump(obj, f, ensure_ascii=True)


async def sleep_msg_clear(msg, seconds):
    await asyncio.sleep(seconds)
    await msg.clear_reactions()
    setting_db.delete('leaderboard', str(msg.id), msg.guild.id)


@bot.event
async def on_ready():
    print("I am Ready!")
#     async with aiofiles.open("ticket_configs.txt", mode="a") as temp:
#         pass
#     async with aiofiles.open("ticket_configs.txt", mode="r") as file:
#         lines = await file.readlines()
#         for line in lines:
#             data = line.split(" ")
#             bot.ticket_configs[int(data[0])] = [int(
#                 data[1]), int(data[2]), int(data[3])]


def get_leaderboard_embed(guild_id, page, members_per_page=10):
    # page == -1 to set it to max_page
    # members[start_idx: end_idx]
    members = profile_db.get_members(guild_id)
    members = sorted(members, key=lambda item: item['score'], reverse=True)
    member_count = len(members)
    max_page = math.ceil(member_count / members_per_page)
    if page > max_page or page <= 0:
        page = max_page

    start_idx = (page - 1) * members_per_page
    end_idx = min(start_idx + members_per_page, member_count)
    # setting_db.save('leaderboard', message_id, page)

    names_str = ''
    for i in range(start_idx, end_idx):
        member = members[i]
        names_str += f"{i + 1} - <@!{member['member_id']}> Scores: {member['score']}\n"
    embed = discord.Embed(title=f"Leaderboard [{page}/{max_page}]")
    embed.add_field(name="Player", value=names_str, inline=False)
    return embed, page


def get_mentions_from_member(members):
    mentions = []
    for member in members:
        if member:
            mentions.append(member.mention)
        else:
            mentions.append('No data available')
    return mentions


def get_game_announce_embed(team_members, game_info, map_name, captain_ids):
    # map_name as argument to make it changeable
    game_id = game_info['game_id']
    team_mentions = []
    for i in range(len(team_members)):  # 2 for old, 3 for assign
        for idx, tm in enumerate(team_members[i]):
            if tm.id in captain_ids:
                team_members[i].pop(idx)
                team_members[i] = [tm] + team_members[i]
                break

    for i in range(len(team_members)):  # 2 for old, 3 for assign
        team_mentions.append(get_mentions_from_member(team_members[i]))

    reg_time = format_datetime(game_info['created_timestamp'])

    embed = discord.Embed(
        title=f"Match:#{game_id:04n} is starting now! [{game_info['region']}]",
        description=f"Map: {map_name}\nCreation time: {reg_time}", color=0x34363d)
    embed.add_field(
        name="「Team 1」", value='Captain: ' + '\n'.join(team_mentions[0]), inline=False)
    embed.add_field(
        name="「Team 2」", value='Captain: ' + '\n'.join(team_mentions[1]), inline=False)
    if len(team_mentions) >= 3:
        to_assign_member_tags = [f'{idx + 1}. {mt}' for idx, mt in enumerate(team_mentions[2])]
        embed.add_field(name="「Players」", value='\n'.join(to_assign_member_tags))
    tags = ['|'.join(tm) for tm in team_mentions]
    tag_str = '\n'.join(tags)
    return tag_str, embed


def get_game_assign_embed(team_members, game_info, map_name, captain_ids):
    # map_name as argument to make it changeable
    game_id = game_info['game_id']
    team_mentions = []
    for i in range(len(team_members)):  # 2 for old, 3 for assign
        for idx, tm in enumerate(team_members[i]):
            if tm.id in captain_ids:
                team_members[i].pop(idx)
                team_members[i] = [tm] + team_members[i]
                break

    for i in range(len(team_members)):  # 2 for old, 3 for assign
        team_mentions.append(get_mentions_from_member(team_members[i]))

    # reg_time = format_datetime(game_info['created_timestamp'])
    embed = discord.Embed(
        title=f"Match:#{game_id:04n} announcement",
        description=f"Map: {map_name}\n", color=0x34363d)
    embed.add_field(
        name="「Team 1」", value='Captain: ' + '\n'.join(team_mentions[0]), inline=False)
    embed.add_field(
        name="「Team 2」", value='Captain: ' + '\n'.join(team_mentions[1]), inline=False)
    if len(team_mentions) >= 3:
        to_assign_member_tags = [f'{idx + 1}. {mt}' for idx, mt in enumerate(team_mentions[2])]
        embed.add_field(name="「Players」", value='\n'.join(to_assign_member_tags))
    tags = ['|'.join(tm) for tm in team_mentions]
    tag_str = '\n'.join(tags)
    return tag_str, embed


def update_leaderboard_page(guild_id, message_id, page):
    setting_db.save('leaderboard', message_id, page, guild_id)


async def update_member_nick(member, p, guild_owner=None):
    if member is None:
        return
    if member != guild_owner:
        nick = f"[{p['score']}] {p['name']}"
        await member.edit(nick=nick)


def format_datetime(dt):
    dt = dt.astimezone(timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# leaderboard
async def leaderboard(ctx):
    page = 1
    guild_id = ctx.guild.id
    async with lock:
        embed, page = get_leaderboard_embed(guild_id, page)
        msg = await ctx.send(embed=embed)
        update_leaderboard_page(guild_id, msg.id, page)
        await msg.add_reaction("⏮")
        await msg.add_reaction("◀")
        await msg.add_reaction("▶")
        await msg.add_reaction("⏭")
        asyncio.get_event_loop().create_task(sleep_msg_clear(msg, 300))


bot.command()(leaderboard)
slash.slash(name='leaderboard', description='Leaderboard')(leaderboard)


# rename
# async def rename(ctx, name: str):
#     guild_id = ctx.guild.id
#     member_id = ctx.author.id
#     member_profile = profile_db.get_profile(member_id, guild_id)
#     nick = f"[{member_profile['score']}] {name}"
#     success = profile_db.edit_name(ctx.author.id, name, guild_id, check_duplicate=True)
#     if success is not None:
#         member = ctx.guild.get_member(ctx.author.id)
#         if member is not None:
#             await member.edit(nick=nick)
#             embed = discord.Embed(
#                 title="Nickname change successful", description=ctx.author.mention, color=0x77bb41)
#             await ctx.send(embed=embed)


# bot.command()(rename)
# slash.slash(name='rename', description='Change nickname')(rename)


# rename
async def _rename(ctx, member: discord.Member, name: str):
    guild_id = ctx.guild.id
    member_id = member.id
    member_profile = profile_db.get_profile(member_id, guild_id)
    nick = f"[{member_profile['score']}] {name}"
    success = profile_db.edit_name(member_id, name, guild_id, check_duplicate=True)
    if success is not None:
        member = ctx.guild.get_member(member_id)
        if member is not None:
            await member.edit(nick=nick)
            embed = discord.Embed(
                title="Nickname change successful", description=member.mention, color=0x77bb41)
            await ctx.send(embed=embed)
            log = ctx.guild.get_channel(log_channel_id)
            await log.send(f"<@!{member_id}> was renamed by <@!{ctx.author.id}>")

@bot.command()
@commands.has_permissions(administrator=admin_lock)
async def rename(ctx, member: discord.Member, name: str):
    await _rename(ctx, member, name)

@slash.slash(name='rename', description='Change nickname')
@commands.has_permissions(administrator=admin_lock)
async def rename(ctx, member: discord.Member, name: str):
    await _rename(ctx, member, name)


# register
async def register(ctx, name=None, link=None):
    async with lock:
        if name is None or link is None:
            embed = discord.Embed(title="❌ Warning: -register <Name> <R6Tracker Unique Link>", color=0xff2600)
            await ctx.send(embed=embed)
            return
        # if not ('r6.tracker.network/profile/' in link or 'tracker.gg/r6siege/' in link):
        if 'r6.tracker.network/r6siege/profile/' not in link:
            embed = discord.Embed(title="❌ Warning: Please enter the correct URL", color=0xff2600)
            await ctx.send(embed=embed)
            return

        member_id = ctx.author.id
        guild_id = ctx.guild.id
        member = ctx.guild.get_member(ctx.author.id)
        role_id = setting_db.getint('role', 'Register', guild_id)
        role = ctx.guild.get_role(role_id)

        member_profile = profile_db.get_profile(member_id, guild_id)
        if member_profile is None:
            dt_now = datetime.now()
            profile_db.add_profile(member_id, name, None, guild_id)
            profile_db.edit_profile(member_id, {'score': 1200}, guild_id)
            # 登錄
            # values = register_fill.get_all_values()
            # df = pd.DataFrame(values[0:], columns=values[0])
            # end_row = df[df["Nickname"].isin([""])].head(1).index.values[0]
            # row = end_row + 1  #最大行敷
            # register_fill.update_value(f"B{row}", f"{name}")
            # register_fill.update_value(f"C{row}", f"{link}")
            # register_fill.update_value(f"D{row}", f"{member_id}")

            embed = discord.Embed(
                title="✅ Register successfully", description=f"Player:{member.mention}\n[R6Tracker]({link})", color=0x96d35f)
            embed.set_thumbnail(url=member.avatar_url)
            reg_time = format_datetime(dt_now)
            embed.set_footer(text=reg_time)
            await ctx.send(embed=embed)
            nick = f"[1200] {name}"
            if ctx.author != ctx.guild.owner:
                await member.edit(nick=nick)
            # await member.add_roles(role)
        else:
            embed = discord.Embed(title="❌ You have already registered", color=0xff2600)
            await ctx.send(embed=embed)


bot.command(aliases=["reg"])(register)
slash.slash(name="register", description="Register")(register)


# profile
async def profile(ctx, player: discord.Member = None):
    member_id = player.id if player is not None else ctx.author.id
    guild_id = ctx.guild.id
    member_profile = profile_db.get_profile(member_id, guild_id)
    if member_profile is not None:
        member = ctx.guild.get_member(member_id)
        win = member_profile['win']
        lose = member_profile['lose']
        reg_time = format_datetime(member_profile['register_timestamp'])
        game = member_profile['game']
        score = member_profile['score']
        winning_streak = member_profile['winning_streak']
        embed = discord.Embed(
            title="Player Profile", description=f"Player:{member.mention}", color=0x00c7fc)
        embed.set_thumbnail(url=member.avatar_url)
        embed.add_field(
            name=f"Scores: {score}\nWins: {win}\nLoses: {lose}\nPlayed matches: {game}\nWinning streak: {winning_streak}",
            value=f"Registration Time: {reg_time}", inline=False)
        await ctx.send(embed=embed)
    elif player is None:
        embed = discord.Embed(title="❌ You haven't registered", color=0xff2600)
        await ctx.send(embed=embed)
    elif player is not None:
        embed = discord.Embed(title="❌This player haven't registered", color=0xff2600)
        await ctx.send(embed=embed)


bot.command(aliases=["p", "P"])(profile)
slash.slash(name='profile', description='Check player profile')(profile)


def get_mentions_from_profiles(guild: discord.Guild, profiles):
    mentions = []
    for p in profiles:
        member = guild.get_member(p['member_id'])
        if member is not None:
            mentions.append(member.mention)
        else:
            mentions.append('No data available')
    return mentions


def get_join_game_embed(guild: discord.Guild, game_id):
    # because of mention, this function need guild object
    # get discord embed from db
    guild_id = guild.id
    game_info, players = game_db.get_game_info(game_id, guild_id)
    region = game_info['region']
    embed = discord.Embed(
        title=f"✅ Successfully joined queue [{len(players)}/10] [{region}]", description=f"Match:#{game_id:04n}", color=0x79ff79)

    mentions = get_mentions_from_profiles(guild, players)
    embed.add_field(
        name="Players:", value='\n'.join(mentions), inline=False)
    return embed


def get_leave_game_embed(guild: discord.Guild, game_id):
    guild_id = guild.id
    game_info, players = game_db.get_game_info(game_id, guild_id)
    region = game_info['region']

    mentions = get_mentions_from_profiles(guild, players)
    player_mentions_str = '\n'.join(mentions) if len(mentions) > 0 else 'No players are in the queue'
    embed = discord.Embed(
        title=f"⛔ Leaving the queue [{len(players)}/10] [{region}]", description=f"Match:#{game_id:04n}", color=0xff2600)
    embed.add_field(
        name="Players:", value=player_mentions_str, inline=False)
    return embed


def get_queue_game_embed(guild: discord.Guild, game_id):
    guild_id = guild.id
    game_info, players = game_db.get_game_info(game_id, guild_id)
    region = game_info['region']

    mentions = get_mentions_from_profiles(guild, players)
    player_mentions_str = '\n'.join(mentions) if len(mentions) > 0 else 'No players are in the queue'
    embed = discord.Embed(
        title=f"R6S SEAS TM [{len(players)}/10] [{region}]", description=f"Match:#{game_id:04n}", color=0x34363d)
    embed.add_field(
        name="Players:", value=player_mentions_str, inline=False)
    return embed


def convert_region_alias(region):
    if region is None:
        return region
    region = region.lower()
    if region in region_names:
        return region
    for k, v in region_name_alias.items():
        if type(v) == list:
            if region in v:
                return k
        elif region == v:
            return k
    return region


dedicated_role_id_attr = "dedicated_role_id"
dedicated_text_channel_id_attr = "dedicated_text_channel_id"
announce_message_id_attr = "announce_message_id"
dedicated_voice_channel_id1_attr = "dedicated_voice_channel_id1"
dedicated_voice_channel_id2_attr = "dedicated_voice_channel_id2"
dedicated_captain_id1_attr = "captain_id1"
dedicated_captain_id2_attr = "captain_id2"


# join
async def join(ctx, region=None):
    region = convert_region_alias(region)  # convert from alias
    if region is None:
        region = region_names[1]
    else:
        if region not in region_names:
            await ctx.send(f"Wrong queue type.")
            # [{'|'.join(region_names)}]
            return
    member_id = ctx.author.id
    guild_id = ctx.guild.id
    open_valid_channel = setting_db.getint('channel', 'Commands', guild_id)
    invite_valid_channel = setting_db.getint('channel', 'Invite_Commands', guild_id)

    if region == 'Random' or region == 'Captain':
        if ctx.channel.id != open_valid_channel:
            return

    if region == invite_random_name or region == invite_captain_name:
        if ctx.channel.id != invite_valid_channel:
            return
    guild = bot.get_guild(guild_id)

    async with lock:
        # Check if member queueing or playing
        member_profile = profile_db.get_profile(member_id, guild_id)
        if member_profile is None:
            return
        member_waiting_playing_games = game_db.get_members(member_id, states=[GameStateTypes.WAITING,
                                                                              GameStateTypes.ASSIGNING,
                                                                              GameStateTypes.PLAYING],
                                                           guild_id=guild_id)

        open_channel = bot.get_channel(setting_db.getint('channel', 'Announcement', guild_id))
        invite_channel = bot.get_channel(setting_db.getint('channel', 'Invite_Announcement', guild_id))
        role = ctx.guild.get_role(setting_db.getint('role', 'Queue', guild_id))
        dedicated_category = guild.get_channel(setting_db.getint('channel', 'Channels', guild_id))
        dedicated_category: discord.CategoryChannel
        if dedicated_category is None:
            embed = discord.Embed(
                title="This server isn't setup channel category yet", color=COLOR_WARNING)
            await ctx.send(embed=embed)
            return

        member = ctx.guild.get_member(ctx.author.id)
        if len(member_waiting_playing_games) == 0:
            # player is free to join
            waiting_games = game_db.get_games(states=GameStateTypes.WAITING, regions=region, guild_id=guild_id)
            if region == invite_captain_name or region == invite_random_name:
                # Additional invite role check
                invite_restrict_role = ctx.guild.get_role(setting_db.getint('role', 'Invite', guild_id))
                if invite_restrict_role is None:
                    embed = discord.Embed(
                        title="This server isn't setup Invite role yet", color=COLOR_WARNING)
                    await ctx.send(embed=embed)
                    return
                if invite_restrict_role not in member.roles:
                    embed = discord.Embed(
                        title="You don't have Invite role", color=COLOR_WARNING)
                    await ctx.send(embed=embed)
                    return

            if len(waiting_games) == 0:
                map_name = None
                game_id = game_db.new_game(map_name, region, None, guild_id)
            else:
                game_id = waiting_games[0]['game_id']

            game_db.add_member_to_game(game_id, member_id, None, guild_id)
            await member.add_roles(role)

            embed = get_join_game_embed(ctx.guild, game_id)
            msg = await ctx.send(embed=embed)

            current_players = game_db.get_game_members_by_id(game_id, guild_id)

            if len(current_players) >= 10:
                # Random
                if region == 'Random':
                    embed.title = f"The queue is full, players are being allocated......"
                    embed.description = f"Match:#{game_id:04n}\nAnnouncement:{open_channel.mention}"
                    embed.colour = 0x34363d
                    await msg.edit(embed=embed)

                    teams = game_db.start_game(game_id, profile_db, guild_id)
                    # teams = game_db.start_assign_game(guild_id, game_id, profile_db)
                    # teams = game_db.get_game_teams(guild_id, game_id)

                    game_info, players = game_db.get_game_info(game_id, guild_id)
                    team_members = []
                    for i in range(len(teams)):
                        team_members.append([])
                        for player in teams[i]:
                            member = ctx.guild.get_member(player['member_id'])
                            team_members[i].append(member)
                            if member:
                                await member.remove_roles(role)

                    red_mentions, blue_mentions = [], []
                    for red_player in teams[0]:
                        red_member = ctx.guild.get_member(red_player['member_id'])
                        if red_member:
                            await red_member.remove_roles(role)
                            red_mentions.append(red_member.mention)
                        else:
                            red_mentions.append('No data available')

                    for blue_player in teams[1]:
                        blue_member = ctx.guild.get_member(blue_player['member_id'])
                        if blue_member:
                            await blue_member.remove_roles(role)
                            blue_mentions.append(blue_member.mention)
                        else:
                            blue_mentions.append('No data available')

                    role_name = f'{game_id} Match Players'
                    dedicated_role = await guild.create_role(name=role_name)
                    score_keeper = guild.get_role(1133412379007401994)
                    overwrites_voice = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False, stream=True),
                        dedicated_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True),
                        score_keeper: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True)
                    }
                    overwrites_text = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        dedicated_role: discord.PermissionOverwrite(view_channel=True),
                        score_keeper: discord.PermissionOverwrite(view_channel=True)
                    }

                    dedicated_text_channel = await dedicated_category.create_text_channel(f'{game_id:04n}-Text',
                                                                                          overwrites=overwrites_text)
                    dedicated_voice_channel1 = await dedicated_category.create_voice_channel(f'{game_id:04n} - Team 1',
                                                                                             overwrites=overwrites_voice)
                    dedicated_voice_channel2 = await dedicated_category.create_voice_channel(f'{game_id:04n} - Team 2',
                                                                                             overwrites=overwrites_voice)
                    game_db.set_game_attr(guild_id, game_id, dedicated_role_id_attr,
                                          str(dedicated_role.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_text_channel_id_attr,
                                          str(dedicated_text_channel.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_voice_channel_id1_attr,
                                          str(dedicated_voice_channel1.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_voice_channel_id2_attr,
                                          str(dedicated_voice_channel2.id))

                    reg_time = format_datetime(datetime.now())
                    map_name = game_info['map']
                    embed = discord.Embed(
                        title=f"Match:#{game_id:04n} is starting now! [{game_info['region']}]",
                        description=f"Map: {map_name}\nCreation time: {reg_time}", color=0x34363d)
                    embed.add_field(
                        name="「Team 1」", value='\n'.join(red_mentions), inline=False)
                    embed.add_field(
                        name="「Team 2」", value='\n'.join(blue_mentions), inline=False)
                    tag_red = '|'.join(red_mentions)
                    tag_blue = '|'.join(blue_mentions)
                    tag_all = f"{tag_red}\n{tag_blue}"

                    for i in range(len(team_members)):
                        for team_member in team_members[i]:
                            team_member: discord.Member
                            if team_member is not None:
                                await team_member.add_roles(dedicated_role)
                    await open_channel.send(content=tag_all, embed=embed)
                    await dedicated_text_channel.send(f'{dedicated_role.mention}', embed=embed)

                # Captain
                if region == 'Captain':
                    embed.title = f"The queue is full, players are being allocated......"
                    embed.description = f"Match:#{game_id:04n}\nAnnouncement:{open_channel.mention}"
                    embed.colour = 0x34363d
                    await msg.edit(embed=embed)

                    # teams = game_db.start_game(game_id, profile_db, guild_id)
                    teams = game_db.start_assign_game(guild_id, game_id, profile_db)
                    teams = game_db.get_game_teams(guild_id, game_id)

                    game_info, players = game_db.get_game_info(game_id, guild_id)
                    team_members = []
                    for i in range(len(teams)):
                        team_members.append([])
                        for player in teams[i]:
                            member = ctx.guild.get_member(player['member_id'])
                            team_members[i].append(member)
                            if member:
                                await member.remove_roles(role)

                    captain_ids = [teams[0][0]['member_id'], teams[1][0]['member_id']]
                    tag_all, embed = get_game_announce_embed(team_members, game_info, 'TBD', captain_ids)
                    announce_msg = await open_channel.send(content=tag_all, embed=embed)
                    game_db.set_game_attr(guild_id, game_id, announce_message_id_attr, announce_msg.id)

                    role_name = f'{game_id} Match Players'
                    dedicated_role = await guild.create_role(name=role_name)
                    score_keeper = guild.get_role(1133412379007401994)
                    overwrites_voice = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False, stream=True),
                        dedicated_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True),
                        score_keeper: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True)
                    }
                    overwrites_text = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        dedicated_role: discord.PermissionOverwrite(view_channel=True),
                        score_keeper: discord.PermissionOverwrite(view_channel=True)
                    }

                    dedicated_text_channel = await dedicated_category.create_text_channel(f'{game_id:04n}-Text',
                                                                                        overwrites=overwrites_text)
                    dedicated_voice_channel1 = await dedicated_category.create_voice_channel(f'{game_id:04n} - Team 1',
                                                                                             overwrites=overwrites_voice)
                    dedicated_voice_channel2 = await dedicated_category.create_voice_channel(f'{game_id:04n} - Team 2',
                                                                                             overwrites=overwrites_voice)
                    game_db.set_game_attr(guild_id, game_id, dedicated_role_id_attr,
                                          str(dedicated_role.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_text_channel_id_attr,
                                          str(dedicated_text_channel.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_voice_channel_id1_attr,
                                          str(dedicated_voice_channel1.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_voice_channel_id2_attr,
                                          str(dedicated_voice_channel2.id))

                    captain_id1 = teams[0][0]['member_id']
                    captain_id2 = teams[1][0]['member_id']
                    game_db.set_game_attr(guild_id, game_id, dedicated_captain_id1_attr, captain_id1)
                    game_db.set_game_attr(guild_id, game_id, dedicated_captain_id2_attr, captain_id2)

                    tag_all, embed = get_game_assign_embed(team_members, game_info, 'TBD', (captain_id1, captain_id2))

                    for i in range(len(team_members)):
                        for team_member in team_members[i]:
                            team_member: discord.Member
                            if team_member is not None:
                                await team_member.add_roles(dedicated_role)
                    mes = await dedicated_text_channel.send(f'{dedicated_role.mention}', embed=embed)

                # Invite-Random
                if region == 'Invite-Random':
                    embed.title = f"The queue is full, players are being allocated......"
                    embed.description = f"Match:#{game_id:04n}\nAnnouncement:{invite_channel.mention}"
                    embed.colour = 0x34363d
                    await msg.edit(embed=embed)

                    teams = game_db.start_game(game_id, profile_db, guild_id)
                    # teams = game_db.start_assign_game(guild_id, game_id, profile_db)
                    # teams = game_db.get_game_teams(guild_id, game_id)

                    game_info, players = game_db.get_game_info(game_id, guild_id)
                    team_members = []
                    for i in range(len(teams)):
                        team_members.append([])
                        for player in teams[i]:
                            member = ctx.guild.get_member(player['member_id'])
                            team_members[i].append(member)
                            if member:
                                await member.remove_roles(role)

                    red_mentions, blue_mentions = [], []
                    for red_player in teams[0]:
                        red_member = ctx.guild.get_member(red_player['member_id'])
                        if red_member:
                            await red_member.remove_roles(role)
                            red_mentions.append(red_member.mention)
                        else:
                            red_mentions.append('No data available')

                    for blue_player in teams[1]:
                        blue_member = ctx.guild.get_member(blue_player['member_id'])
                        if blue_member:
                            await blue_member.remove_roles(role)
                            blue_mentions.append(blue_member.mention)
                        else:
                            blue_mentions.append('No data available')

                    role_name = f'{game_id} Match players'
                    dedicated_role = await guild.create_role(name=role_name)
                    score_keeper = guild.get_role(1133412379007401994)
                    overwrites_voice = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False, stream=True),
                        dedicated_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True),
                        score_keeper: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True)
                    }
                    overwrites_text = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        dedicated_role: discord.PermissionOverwrite(view_channel=True),
                        score_keeper: discord.PermissionOverwrite(view_channel=True)
                    }

                    dedicated_text_channel = await dedicated_category.create_text_channel(f'{game_id:04n}-Text',
                                                                                          overwrites=overwrites_text)
                    dedicated_voice_channel1 = await dedicated_category.create_voice_channel(f'{game_id:04n} - Team 1',
                                                                                             overwrites=overwrites_voice)
                    dedicated_voice_channel2 = await dedicated_category.create_voice_channel(f'{game_id:04n} - Team 2',
                                                                                             overwrites=overwrites_voice)
                    game_db.set_game_attr(guild_id, game_id, dedicated_role_id_attr,
                                          str(dedicated_role.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_text_channel_id_attr,
                                          str(dedicated_text_channel.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_voice_channel_id1_attr,
                                          str(dedicated_voice_channel1.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_voice_channel_id2_attr,
                                          str(dedicated_voice_channel2.id))

                    reg_time = format_datetime(datetime.now())
                    map_name = game_info['map']
                    embed = discord.Embed(
                        title=f"Match:#{game_id:04n} is starting now! [{game_info['region']}]",
                        description=f"Map: {map_name}\nCreation time: {reg_time}", color=0x34363d)
                    embed.add_field(
                        name="「Team 1」", value='\n'.join(red_mentions), inline=False)
                    embed.add_field(
                        name="「Team 2」", value='\n'.join(blue_mentions), inline=False)
                    tag_red = '|'.join(red_mentions)
                    tag_blue = '|'.join(blue_mentions)
                    tag_all = f"{tag_red}\n{tag_blue}"

                    for i in range(len(team_members)):
                        for team_member in team_members[i]:
                            team_member: discord.Member
                            if team_member is not None:
                                await team_member.add_roles(dedicated_role)
                    await invite_channel.send(content=tag_all, embed=embed)
                    await dedicated_text_channel.send(f'{dedicated_role.mention}', embed=embed)

                # Invite-Captain
                if region == 'Invite-Captain':
                    embed.title = f"The queue is full, players are being allocated......"
                    embed.description = f"Match:#{game_id:04n}\nAnnouncement:{invite_channel.mention}"
                    embed.colour = 0x34363d
                    await msg.edit(embed=embed)

                    # teams = game_db.start_game(game_id, profile_db, guild_id)
                    teams = game_db.start_assign_game(guild_id, game_id, profile_db)
                    teams = game_db.get_game_teams(guild_id, game_id)

                    game_info, players = game_db.get_game_info(game_id, guild_id)
                    team_members = []
                    for i in range(len(teams)):
                        team_members.append([])
                        for player in teams[i]:
                            member = ctx.guild.get_member(player['member_id'])
                            team_members[i].append(member)
                            if member:
                                await member.remove_roles(role)

                    captain_ids = [teams[0][0]['member_id'], teams[1][0]['member_id']]
                    tag_all, embed = get_game_announce_embed(team_members, game_info, 'TBD', captain_ids)
                    announce_msg = await invite_channel.send(content=tag_all, embed=embed)
                    game_db.set_game_attr(guild_id, game_id, announce_message_id_attr, announce_msg.id)

                    role_name = f'{game_id} Match Players'
                    dedicated_role = await guild.create_role(name=role_name)
                    score_keeper = guild.get_role(1133412379007401994)
                    overwrites_voice = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False, stream=True),
                        dedicated_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True),
                        score_keeper: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True)
                    }
                    overwrites_text = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        dedicated_role: discord.PermissionOverwrite(view_channel=True),
                        score_keeper: discord.PermissionOverwrite(view_channel=True)
                    }

                    dedicated_text_channel = await dedicated_category.create_text_channel(f'{game_id:04n}-Text',
                                                                                        overwrites=overwrites_text)
                    dedicated_voice_channel1 = await dedicated_category.create_voice_channel(f'{game_id:04n} - Team 1',
                                                                                             overwrites=overwrites_voice)
                    dedicated_voice_channel2 = await dedicated_category.create_voice_channel(f'{game_id:04n} - Team 2',
                                                                                             overwrites=overwrites_voice)
                    game_db.set_game_attr(guild_id, game_id, dedicated_role_id_attr,
                                          str(dedicated_role.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_text_channel_id_attr,
                                          str(dedicated_text_channel.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_voice_channel_id1_attr,
                                          str(dedicated_voice_channel1.id))
                    game_db.set_game_attr(guild_id, game_id, dedicated_voice_channel_id2_attr,
                                          str(dedicated_voice_channel2.id))

                    captain_id1 = teams[0][0]['member_id']
                    captain_id2 = teams[1][0]['member_id']
                    game_db.set_game_attr(guild_id, game_id, dedicated_captain_id1_attr, captain_id1)
                    game_db.set_game_attr(guild_id, game_id, dedicated_captain_id2_attr, captain_id2)

                    tag_all, embed = get_game_assign_embed(team_members, game_info, 'TBD', (captain_id1, captain_id2))

                    for i in range(len(team_members)):
                        for team_member in team_members[i]:
                            team_member: discord.Member
                            if team_member is not None:
                                await team_member.add_roles(dedicated_role)
                    mes = await dedicated_text_channel.send(f'{dedicated_role.mention}', embed=embed)

        else:
            embed = discord.Embed(title="❌ You have joined the queue or already started", color=0xff2600)
            await ctx.send(embed=embed)


bot.command(aliases=["j", "J"])(join)
slash.slash(name='join', description='Join queue',
            options=[
                create_option(
                    name='region',
                    description='Select the type of queue',
                    required=False,
                    option_type=SlashCommandOptionType.STRING,
                    choices=[create_choice(name=region_name, value=region_name) for region_name in region_names]
                )
            ])(join)


# pick
async def pick(ctx, member_idx: int):
    member_id = ctx.author.id
    guild_id = ctx.guild.id
    member_assigning_games = game_db.get_members(member_id, states=[GameStateTypes.ASSIGNING],
                                                 guild_id=guild_id)
    if len(member_assigning_games) < 1:
        return
    game_id = member_assigning_games[0]['game_id']
    game_info, players = game_db.get_game_info(game_id, guild_id)
    author_game_info = None
    for player in players:
        if player['member_id'] == ctx.author.id:
            author_game_info = player

    game_text_channel_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_text_channel_id_attr)
    if ctx.channel.id != game_text_channel_id:
        return

    game_captain_id1 = game_db.get_game_attr_int(guild_id, game_id, dedicated_captain_id1_attr)
    game_captain_id2 = game_db.get_game_attr_int(guild_id, game_id, dedicated_captain_id2_attr)

    teams = game_db.get_game_teams(guild_id, game_id)

    assigning_team = 1 if len(teams[0]) <= len(teams[1]) else 2
    # assigning_team = 1 if len(player_pool) == 8 or len(player_pool) == 5 or len(player_pool) == 3 or len(player_pool) == 1 else 2

    assigning_captain_id = game_captain_id1 if assigning_team == 1 else game_captain_id2
    if ctx.author.id not in [game_captain_id1, game_captain_id2]:
        embed = discord.Embed(title="❌ You have no permission to use this command", color=COLOR_WARNING)
        await ctx.send(embed=embed)
        return
    if ctx.author.id != assigning_captain_id:
        embed = discord.Embed(title="❌ Please wait for your opponent to choose a player", color=COLOR_WARNING)
        await ctx.send(embed=embed)
        return
    player_pool = teams[2]
    if member_idx > len(player_pool) or member_idx < 1:
        embed = discord.Embed(title="❌ Wrong number", color=COLOR_WARNING)
        await ctx.send(embed=embed)
        return

    to_assign_player = player_pool.pop(member_idx - 1)
    teams[assigning_team - 1].append(to_assign_player)
    game_db.set_members_team(game_id, [to_assign_player], assigning_team, guild_id)
    teams = game_db.get_game_teams(guild_id, game_id)
    team_members = []
    for i in range(len(teams)):
        team_members.append([])
        for player in teams[i]:
            member = ctx.guild.get_member(player['member_id'])
            team_members[i].append(member)
    if len(team_members[2]) == 0:
        team_members.pop(2)
        map_name = game_info['map']
        game_db.set_game_state(game_id, GameStateTypes.PLAYING, guild_id)
        if game_info['region'] == 'Invite-Captain':
            announce_channel = bot.get_channel(setting_db.getint('channel', 'Invite_Announcement', guild_id))
            game_announce_message_id = game_db.get_game_attr_int(guild_id, game_id, announce_message_id_attr)
            game_announce_message = await announce_channel.fetch_message(game_announce_message_id)
            tag_all, embed = get_game_announce_embed(team_members, game_info, map_name, (game_captain_id1, game_captain_id2))
            game_announce_message: discord.Message
            await game_announce_message.edit(content=tag_all, embed=embed)
        else:
            announce_channel = bot.get_channel(setting_db.getint('channel', 'Announcement', guild_id))
            game_announce_message_id = game_db.get_game_attr_int(guild_id, game_id, announce_message_id_attr)
            game_announce_message = await announce_channel.fetch_message(game_announce_message_id)
            tag_all, embed = get_game_announce_embed(team_members, game_info, map_name, (game_captain_id1, game_captain_id2))
            game_announce_message: discord.Message
            await game_announce_message.edit(content=tag_all, embed=embed)
    else:
        map_name = 'TBD'
    tag_all, embed = get_game_assign_embed(team_members, game_info, map_name, (game_captain_id1, game_captain_id2))
    await ctx.send(embed=embed)


bot.command()(pick)
slash.slash(name='pick', description='Select a player',
            options=[
                create_option(
                    name='member_idx',
                    description='Select a player number',
                    required=True,
                    option_type=SlashCommandOptionType.INTEGER,
                )
            ])(pick)


# leave
async def leave(ctx):
    async with lock:
        guild = ctx.guild
        guild_id = guild.id
        member_id = ctx.author.id
        open_valid_channel = bot.get_channel(setting_db.getint('channel', 'Commands', guild_id))
        invite_valid_channel = bot.get_channel(setting_db.getint('channel', 'Invite_Commands', guild_id))
        if ctx.channel != open_valid_channel:
            if ctx.channel != invite_valid_channel:
                return

        member = ctx.guild.get_member(member_id)
        role = ctx.guild.get_role(setting_db.getint('role', 'Queue', guild_id))

        member_waiting_games = game_db.get_member_waiting_game(member_id, guild_id)
        for game_info in member_waiting_games:
            game_id = game_info['game_id']
            game_db.remove_member_from_game(game_id, member_id, guild_id)
            await member.remove_roles(role)
            embed = get_leave_game_embed(guild, game_id)
            await ctx.send(embed=embed)


bot.command(aliases=["l"])(leave)
slash.slash(name='leave', description='Leave queue')(leave)


# queue
async def _queue(ctx, region: str):
    if region is not None:
        region = convert_region_alias(region)  # convert from alias
    else:
        region = region_names[1]

    if region is not None and region not in region_names:
#         await ctx.send(f"Wrong region name [{'|'.join(region_names)}]")
        return
    guild = ctx.guild
    guild_id = guild.id
    open_valid_channel = setting_db.getint('channel', 'Commands', guild_id)
    invite_valid_channel = setting_db.getint('channel', 'Invite_Commands', guild_id)

    if region == 'Random' or region == 'Captain':
        if ctx.channel.id != open_valid_channel:
            return

    if region == invite_random_name or region == invite_captain_name:
        if ctx.channel.id != invite_valid_channel:
            return

    async with lock:
        waiting_games = game_db.get_games(states=GameStateTypes.WAITING, regions=region, guild_id=guild_id)
        if len(waiting_games) > 0:
            for g in waiting_games:
                game_id = g['game_id']
                embed = get_queue_game_embed(guild, game_id)
                await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title=f"❌ No players in queue", color=0xff2600)
            await ctx.send(embed=embed)


@bot.command(aliases=["q"])
async def queue(ctx, region=None):
    await _queue(ctx, region)


@slash.slash(name="queue", description="Check queue", options=[
    create_option(
        name='region',
        description='Select the type of queue',
        required=False,
        option_type=SlashCommandOptionType.STRING,
        choices=[create_choice(name=region_name, value=region_name) for region_name in region_names]
    )
])
async def queue(ctx, region=None):
    await _queue(ctx, region)


# admin command


# game
async def _game(ctx, game_id: int, winner_team: str):
    async with lock:
        guild = ctx.guild
        guild_id = guild.id
        open_channel = bot.get_channel(setting_db.getint('channel', 'Results', guild_id))
        invite_channel = bot.get_channel(setting_db.getint('channel', 'Invite_Results', guild_id))
        admin_role = ctx.guild.get_role(setting_db.getint('role', 'Admins', guild_id))
        member = ctx.guild.get_member(ctx.author.id)
        # if admin_lock and admin_role not in member.roles:
        #     return
        game_info = game_db.get_game_by_id(game_id, guild_id)
        if game_info is None:
            embed = discord.Embed(title=f"Warning: `[{game_id:04n}]` match doesn't exist", color=0xff2600)
            await ctx.send(embed=embed)
            return
        if game_info['state'] != GameStateTypes.PLAYING:
            if game_info['state'] == GameStateTypes.WAITING:
                embed = discord.Embed(title=f"Warning: `[{game_id:04n}]` haven't started yet", color=0xff2600)
            elif game_info['state'] == GameStateTypes.FINISHED:
                embed = discord.Embed(title=f"Warning: `[{game_id:04n}]` already finished", color=0xff2600)
            else:
                embed = discord.Embed(title=f"Warning: `[{game_id:04n}]` {game_info['state']}", color=0xff2600)
            await ctx.send(embed=embed)
            return

        winner_team_id = team_name_id[winner_team]
        embed = discord.Embed(title="Loading......", color=0x34363d)
        if game_info['region'] == 'Invite-Captain' or game_info['region'] == 'Invite-Random':
            msg = await invite_channel.send(embed=embed)
        else:
            msg = await open_channel.send(embed=embed)
        embed = discord.Embed(
            title=f"Winner:「{winner_team}」🏆", description=f"Match: #{game_id:04n}", color=0xf5ec00)

        game_db.finish_game(game_id, guild_id)
        for team_name, team_id in team_name_id.items():
            team_members = game_db.get_game_members_by_id(game_id, guild_id, team_id)
            mentions = []

            for tm in team_members:
                member_id = tm['member_id']
                member = guild.get_member(member_id)
                p = profile_db.get_profile(member_id, guild_id)
                if member:
                    mentions.append(member.mention)
                else:
                    mentions.append('No data available')
                    continue
                if team_id == winner_team_id:
                    # win
                    if game_info['region'] == '快速':
                        win_score = 6
                        new_winning_streak = p['winning_streak']
                    else:
                        win_score = 11
                        new_winning_streak = p['winning_streak'] + 1

                    new_profile = {
                        'score': max(p['score'] + win_score, 0),
                        'win': p['win'] + 1,
                        'game': p['game'] + 1,
                        'winning_streak': new_winning_streak
                    }
                    # if new_profile['winning_streak'] >= 5:
                    #     new_profile['score'] += 5
                else:
                    # loss
                    if game_info['region'] == '快速':
                        loss_score = 5
                        new_winning_streak = p['winning_streak']
                    else:
                        loss_score = 9
                        new_winning_streak = 0
                    new_profile = {
                        'score': max(p['score'] - loss_score, 0),
                        'lose': p['lose'] + 1,
                        'game': p['game'] + 1,
                        'winning_streak': new_winning_streak
                    }
                profile_db.edit_profile(member_id, new_profile, guild_id)
                new_profile = profile_db.get_profile(member_id, guild_id)
                await update_member_nick(member, new_profile, ctx.guild.owner)

            mention_str = '\n'.join(mentions) if mentions else 'No players'
            if team_id == winner_team_id:
                embed.add_field(name=f"🥇「{team_name}」", value=mention_str, inline=False)
            else:
                embed.add_field(name=f"「{team_name}」", value=mention_str, inline=False)

        await msg.edit(embed=embed)
        game_role_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_role_id_attr)
        game_text_channel_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_text_channel_id_attr)
        game_voice_channel1_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_voice_channel_id1_attr)
        game_voice_channel2_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_voice_channel_id2_attr)
        await guild.get_channel(game_text_channel_id).delete()
        await guild.get_channel(game_voice_channel1_id).delete()
        await guild.get_channel(game_voice_channel2_id).delete()
        await guild.get_role(game_role_id).delete()
        log = ctx.guild.get_channel(log_channel_id)
        await log.send(f"Match {game_id:04n} was ended by <@!{ctx.author.id}>")


@bot.command()
@commands.has_role(1133412379007401994)
async def game(ctx, game_id: int, team: str):
    await _game(ctx, game_id, team)


@slash.slash(name="game", description="結算成績",
             options=[
                 create_option(
                     name='game_id',
                     description='場次',
                     required=True,
                     option_type=SlashCommandOptionType.INTEGER,
                 ),
                 create_option(
                     name='team',
                     description='勝利隊伍',
                     required=True,
                     option_type=SlashCommandOptionType.STRING,
                     choices=[create_choice(name=team_name, value=team_name) for team_name in
                              team_name_id.keys()]
                 )])
@commands.has_role(1133412379007401994)
async def game(ctx, game_id: int, team: str):
    await _game(ctx, game_id, team)


# setchannel
async def _setchannel(ctx, channel_type, channel: discord.TextChannel):
    guild_id = ctx.guild.id

    if channel_type in valid_channel_types:
        setting_db.save('channel', channel_type, channel.id, guild_id)

        embed = discord.Embed(title=f"{channel_type} has been setup as",
                              description=channel.mention, color=0x77bb41)
        await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=admin_lock)
async def setchannel(ctx, channel_type, channel: discord.TextChannel):
    await _setchannel(ctx, channel_type, channel)


@slash.slash(name='setchannel', description="Setup channel type",
             options=[
                 create_option(
                     name='channel_type',
                     description='Type',
                     required=True,
                     option_type=SlashCommandOptionType.STRING,
                     choices=[create_choice(name=channel_type, value=channel_type) for channel_type in
                              valid_channel_types]
                 ),
                 create_option(
                     name='channel',
                     description='Channel',
                     required=True,
                     option_type=SlashCommandOptionType.CHANNEL
                 )])
@commands.has_permissions(administrator=admin_lock)
async def setchannel(ctx, channel_type, channel: discord.TextChannel):
    await _setchannel(ctx, channel_type, channel)


# set_role
async def _setrole(ctx, role_type: str, role: discord.Role):
    guild_id = ctx.guild.id
    if role_type in valid_role_types:
        setting_db.save('role', role_type, str(role.id), guild_id)
        embed = discord.Embed(
            title=f"Role {role_type} has been setup as", description=role.mention, color=0x77bb41)
        await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=admin_lock)
async def setrole(ctx, role_type: str, role: discord.Role):
    await _setrole(ctx, role_type, role)


@slash.slash(name='setrole', description='Setup role type',
             options=[
                 create_option(
                     name='role_type',
                     description='Type',
                     required=True,
                     option_type=SlashCommandOptionType.STRING,
                     choices=[create_choice(name=role_type, value=role_type) for role_type in valid_role_types]
                 ),
                 create_option(
                     name='role',
                     description='Role',
                     required=True,
                     option_type=SlashCommandOptionType.ROLE
                 )])
@commands.has_permissions(administrator=admin_lock)
async def setrole(ctx, role_type: str, role: discord.Role):
    await _setrole(ctx, role_type, role)


# set_setting
async def _setval(ctx, setting_type: str, setting_value: str):
    guild_id = ctx.guild.id
    if setting_type in valid_setting_types:
        setting_db.save('setting', setting_type, setting_value, guild_id)
        embed = discord.Embed(
            title=f"{setting_type} has been setup as", description=setting_value, color=0x77bb41)
        await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=admin_lock)
async def setval(ctx, setting_type: str, setting_value: str):
    await _setval(ctx, setting_type, setting_value)


@slash.slash(name='setval', description='Setup values',
             options=[
                 create_option(
                     name='setting_type',
                     description='Type',
                     required=True,
                     option_type=SlashCommandOptionType.STRING,
                     choices=[create_choice(name=setting_type, value=setting_type) for setting_type in
                              valid_setting_types]
                 ),
                 create_option(
                     name='setting_value',
                     description='Values',
                     required=True,
                     option_type=SlashCommandOptionType.STRING
                 )])
@commands.has_permissions(administrator=admin_lock)
async def setval(ctx, setting_type: str, setting_value: str):
    await _setval(ctx, setting_type, setting_value)


# raid
async def _raid(ctx):
    guild_id = ctx.guild.id
    valid_channel_id = setting_db.getint('channel', 'Commands', guild_id)
    # valid_channel = bot.get_channel(setting_db.getint('channel', '指令', guild_id))
    if ctx.channel.id != valid_channel_id:
        return
    last_used_time = setting_db.get('setting', 'Raid cooldown', guild_id=guild_id)
    raid_cooldown_minutes = setting_db.getint('setting', 'Raid cooldown', guild_id=guild_id)

    if last_used_time is not None:
        last_used_time = datetime.strptime(last_used_time, '%Y-%m-%d %H:%M:%S')
        cooldown = datetime.now() - last_used_time
        if raid_cooldown_minutes is not None:
            raid_time_delta = timedelta(minutes=raid_cooldown_minutes)
            if cooldown < raid_time_delta:
                time_diff = raid_time_delta - cooldown
                await ctx.reply(f'🔕 Raid is cooling down（Remaining{int(time_diff.total_seconds() // 60)}minutes'
                                f'{int(time_diff.total_seconds() % 60)}秒）')
                return
    mention_role_id = setting_db.getint('role', 'Raid', guild_id=guild_id)
    # embed = discord.Embed(title=f"🔔 <@{ctx.author.id}> 使用了揪團指令。", color=0x77bb41)
    message = f"🔔 <@&{mention_role_id}> <@{ctx.author.id}> used raid"
    setting_db.save('setting', 'Raid cooldown', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), guild_id=guild_id)
    await ctx.send(message)


@bot.command()
async def raid(ctx):
    await _raid(ctx)


# @slash.slash(name='raid', description='揪團提醒')
# async def raid(ctx):
#     await _raid(ctx)


# cancel
async def _cancel(ctx, game_id: int, reason: str = None):
    async with lock:
        await ctx.defer()
        guild = ctx.guild
        guild_id = guild.id
        member = ctx.guild.get_member(ctx.author.id)
        # role_manager = ctx.guild.get_role(setting_db.getint('role', 'Admins', guild_id))
        # admin check, but actually this command already requires admin.
        # if admin_lock and role_manager not in member.roles:
        #     return
        role_match = ctx.guild.get_role(setting_db.getint('role', 'Queue', guild_id))
        game_info = game_db.get_game_by_id(game_id, guild_id)
        if game_info is None:
            embed = discord.Embed(title=f"Not found this match❌ [{game_id:04n}]", color=0xff2600)
            await ctx.send(embed=embed)
            return

        if game_info['state'] not in (GameStateTypes.WAITING, GameStateTypes.PLAYING,
                                      GameStateTypes.ASSIGNING):
            embed = discord.Embed(title=f"Warning: `[{game_id:04n}]` {game_info['state']} cannot be cancelled", color=0xff2600)
            await ctx.send(embed=embed)
            return

        removed_members = game_db.remove_game(game_id, guild_id)
        for m in removed_members:
            member_id = m['member_id']
            member = guild.get_member(member_id)
            if member is not None:
                await member.remove_roles(role_match)

        game_role_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_role_id_attr)
        game_text_channel_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_text_channel_id_attr)
        game_voice_channel1_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_voice_channel_id1_attr)
        game_voice_channel2_id = game_db.get_game_attr_int(guild_id, game_id, dedicated_voice_channel_id2_attr)
        if game_text_channel_id:
            await guild.get_channel(game_text_channel_id).delete()
        if game_voice_channel1_id:
            await guild.get_channel(game_voice_channel1_id).delete()
        if game_voice_channel2_id:
            await guild.get_channel(game_voice_channel2_id).delete()
        if game_role_id:
            await guild.get_role(game_role_id).delete()

        log = ctx.guild.get_channel(log_channel_id)
        if reason:
            await log.send(f"Match {game_id:04n} was cancelled by <@!{ctx.author.id}> because **{reason}**")
        else:
            await log.send(f"Match {game_id:04n} was cancelled by <@!{ctx.author.id}>")

        embed = discord.Embed(
            title=f"Cancelled", description=f"Match:#{game_id:04n}", color=0x34363d)
        await ctx.send(embed=embed)


@bot.command()
@commands.has_role(1133412379007401994)
async def cancel(ctx, game_id: int, reason: str = None):
    await _cancel(ctx, game_id, reason)


# slash command
@slash.slash(name="cancel", description="Cancel match")
@commands.has_role(1133412379007401994)
async def cancel(ctx, game_id: int, reason: str = None):
    await _cancel(ctx, game_id, reason)


@slash.slash(name='reset', description="Reset player scores")
@commands.has_permissions(administrator=admin_lock)
async def reset(ctx, member: discord.Member):
    guild_id = ctx.guild.id
    member_id = member.id
    p = profile_db.get_profile(member_id, guild_id)
    if p is not None:
        profile_db.reset_season_data(member_id, guild_id)
        p = profile_db.get_profile(member_id, guild_id)
        embed = discord.Embed(
            title="Already reset this player scores", description=member.mention, color=0x77bb41)
        await ctx.send(embed=embed)
        nick = f"[{p['score']}] {p['name']}"
        await member.edit(nick=nick)
    else:
        embed = discord.Embed(title="This player isn't registered", color=0xff2600)
        await ctx.send(embed=embed)


async def _resetall(ctx):
    embed = discord.Embed(title="Are you sure you want to reset all player scores? [y]", color=0x77bb41)
    await ctx.send(embed=embed)
    msg = await bot.wait_for('message', check=lambda message: message.author == ctx.author)
    if msg.content.lower() != 'y':
        embed = discord.Embed(title="Cancelled", color=0x77bb41)
        await ctx.send(embed=embed)
        return
    embed = discord.Embed(title="Resetting all player scores...", color=0x77bb41)
    msg = await ctx.send(embed=embed)

    guild_id = ctx.guild.id
    profile_db.reset_all_season_data(guild_id)
    profiles = profile_db.get_members(guild_id)
    for p in profiles:
        member_id = p['member_id']
        member = ctx.guild.get_member(member_id)
        if member is None:
            continue
        if member != ctx.guild.owner:
            nick = f"[{p['score']}] {p['name']}"
            await member.edit(nick=nick)
    embed = discord.Embed(title="All player scores have been reset", color=0x77bb41)
    await msg.edit(embed=embed)


@slash.slash(name='resetall', description="Reset all player scores")
@commands.has_permissions(administrator=admin_lock)
async def resetall(ctx):
    await _resetall(ctx)


@bot.command(name='resetall', description="Reset all player scores")
@commands.has_permissions(administrator=admin_lock)
async def resetall(ctx):
    await _resetall(ctx)


# async def _testing9(ctx, region: str = None):
#     print('testing9', region)
#     game_db.testing_add_9_game(region, ctx.guild.id)


# @bot.command(name='testing9', description="add game with 9 players")
# @commands.has_permissions(administrator=admin_lock)
# async def testing9(ctx, region: str = None):
#     await _testing9(ctx, region)


# event
@bot.event
async def on_raw_reaction_add(payload):
    guild_id = payload.guild_id
    message_id = payload.message_id
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(message_id)
    user = bot.get_user(payload.user_id)
    page = setting_db.getint('leaderboard', str(message_id), guild_id)
    if page is not None and user != bot.user:
        await message.remove_reaction(payload.emoji, user)
        if str(payload.emoji) == "⏮":
            page = 1
        elif str(payload.emoji) == "⏭":
            page = -1
        elif str(payload.emoji) == "◀" and page >= 1:
            page -= 1
        elif str(payload.emoji) == "▶":
            page += 1
        embed, page = get_leaderboard_embed(guild_id, page)  # return the embed and corrected page
        update_leaderboard_page(guild_id, str(message_id), page)
        await message.edit(embed=embed)

#     if payload.member.id != bot.user.id and str(payload.emoji) == u"📩":
#         msg_id, channel_id, category_id = bot.ticket_configs[payload.guild_id]

#         if payload.message_id == msg_id:
#             guild = bot.get_guild(payload.guild_id)

#             for category in guild.categories:
#                 if category.id == category_id:
#                     break

#             channel = guild.get_channel(channel_id)

#             with open("ticket.txt", "r") as r:
#                 ticket_num = int(r.read())

#             ticket_channel = await category.create_text_channel(f"檢舉案件-{ticket_num}",
#                                                                 topic=f"A ticket for {payload.member.display_name}.",
#                                                                 permission_synced=True)
#             ticket_num += 1
#             ticket_num = str(ticket_num)

#             with open("ticket.txt", "w") as w:
#                 w.writelines(ticket_num)

#             await ticket_channel.set_permissions(payload.member, read_messages=True, send_messages=True)

#             message = await channel.fetch_message(msg_id)
#             await message.remove_reaction(payload.emoji, payload.member)

#             await ticket_channel.send(
#                 f"{payload.member.mention} 你已成功開啟檢舉案件，請在此頻道完整說明事情始末並附上證據。\n{manager_role_memtion}將會盡快回復此案件，完整的證據說明可以增加處理效率。")


# @bot.command()
# @commands.has_permissions(administrator=True)
# async def ticket(ctx, msg: discord.Message = None, category: discord.CategoryChannel = None):
#     if msg is None or category is None:
#         await ctx.channel.send("Failed to configure the ticket as an argument was not given or was invalid.")
#         return

#     bot.ticket_configs[ctx.guild.id] = [
#         msg.id, msg.channel.id, category.id]  # this resets the configuration

#     async with aiofiles.open("ticket_configs.txt", mode="r") as file:
#         ticket_data = await file.readlines()

#     async with aiofiles.open("ticket_configs.txt", mode="w") as file:
#         await file.write(f"{ctx.guild.id} {msg.id} {msg.channel.id} {category.id}\n")

#         for line in ticket_data:
#             if int(line.split(" ")[0]) != ctx.guild.id:
#                 await file.write(line)

#     await msg.add_reaction(u"📩")
#     await ctx.channel.send("Successfully configured the ticket system.")


@slash.slash(name="score", description="Modify score")
@commands.has_permissions(administrator=admin_lock)
async def score(ctx, member: discord.Member, sym: str, num: str):
    await ctx.defer()
    num = int(num)
    guild_id = ctx.guild.id
    member_id = member.id
    member = ctx.guild.get_member(member_id)

    p = profile_db.get_profile(member_id, guild_id)
    if p is None:
        await ctx.send("no user")
        return
    from_score = p['score']
    new_profile = {
        'score': p['score']
    }
    if sym == "+":
        new_profile['score'] += num
    elif sym == "-":
        new_profile['score'] -= num
    profile_db.edit_profile(member_id, new_profile, guild_id)
    p = profile_db.get_profile(member_id, guild_id)
    await update_member_nick(member, p, ctx.guild.owner)
    await ctx.send(f"success, `[{from_score}]` -> `[{p['score']}]`")


# @slash.slash(name="offTicket", description="清除權限")
# async def offTicket(ctx, channel: discord.TextChannel, user: discord.Member):
#     await channel.set_permissions(user, overwrite=None)
#     await ctx.send("清除成功")


# @bot.command()
# @commands.has_permissions(administrator=True)
# async def test(ctx, game_id: str):
#     guild_id = ctx.guild.id
#     teams = game_db.get_game_teams(guild_id, game_id)
#     await ctx.send(f"{len(teams[0])}\n\n{len(teams[1])}\n\n{len(teams[2])}")


async def schedule_clear_game_member():
    gs = setting_db.get_all_guild('setting', 'Queuing time limit')
    time_now = datetime.now()
    for guild_id, value in gs:
        guild_id = int(guild_id)
        guild = bot.get_guild(guild_id)
        queue_role_id = setting_db.getint('role', 'Queue', guild_id)
        if queue_role_id is not None:
            queue_role = guild.get_role(queue_role_id)
        else:
            queue_role = None
        value = int(value)
        time_interval = timedelta(minutes=value)
        valid_channel_id = setting_db.getint('channel', 'Commands', guild_id)
        valid_channel = guild.get_channel(valid_channel_id)
        games = game_db.get_games(states=GameStateTypes.WAITING, guild_id=guild_id)
        for g in games:
            game_info, players = game_db.get_game_info(g['game_id'], guild_id=guild_id)
            game_id = game_info['game_id']
            for p in players:
                mid = p['member_id']
                member = guild.get_member(mid)
                waited_time = time_now - p['add_time']
                if waited_time >= time_interval:
                    game_db.remove_member_from_game(game_id, mid, guild_id=guild_id)
                    await member.remove_roles(queue_role)
                    await valid_channel.send(f'⛔ [{len(players) - 1}/10] <@{mid}> left the queue due to long waiting time.')


async def crontab_loop():
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(15)
        except Exception as e:
            traceback.print_exc()
            await asyncio.sleep(5)


if __name__ == '__main__':
    schedule.every(1).minutes.do(lambda: bot.loop.create_task(schedule_clear_game_member()))
    bot.loop.create_task(crontab_loop())
    bot.run(TOKEN)
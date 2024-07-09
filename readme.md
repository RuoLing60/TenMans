```
TABLE setting 儲存設定
{
    guild_id: int
    type: str  # role, channel, leaderboard
    name: str  # 配對, 註冊, 管理
    value: str
    UNIQUE(guild_id, type, name)
}

TABLE game 儲存遊戲資料(配對中、進行中、已完成)
{
    guild_id: int
    game_id: int
    map: str
    region: str
    state: str
    winner: int
    
    created_timestamp: timestamp
    UNIQUE(game_id, guild_id)
}

TABLE game_member
{
    guild_id: int
    game_id: int
    member_id: int
    team: int
    UNIQUE(guild_id, game_id, member_id)
}

TABLE profile
{
    guild_id: int
    member_id: int
    name: str
    register_timestamp: timestamp
    
    score: int
    lose: int
    win: int
    game: int
    winning_streak: int
    
    UNIQUE(guild_id, member_id)
}

```
import discord
from discord.ext import commands
import os

# 1. 봇 기본 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="", intents=intents)

# 2. 파일 기준 단어장 로드 (경로 자동 추적 + 대용량 인코딩 방어)
WORD_DICT = []
FILE_NAME = "words.txt"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, FILE_NAME)

if os.path.exists(FILE_PATH):
    try:
        with open(FILE_PATH, "r", encoding="utf-8-sig") as f:
            WORD_DICT = [w.strip() for w in f.read().split() if w.strip()]
    except UnicodeDecodeError:
        with open(FILE_PATH, "r", encoding="cp949") as f:
            WORD_DICT = [w.strip() for w in f.read().split() if w.strip()]
            
    print(f"✅ 단어장 파일 로드 완료! 위치: {FILE_PATH}")
    print(f"📊 총 {len(WORD_DICT)}개의 단어가 등록되었습니다.")
else:
    print(f"⚠️ 경고: {FILE_NAME} 파일이 없습니다! 아래 경로에 메모장을 만들어주세요.")
    print(f"📁 필수 파일 위치: {FILE_PATH}")

# 3. 전역 데이터 구조 (채널별 독립 관리)
normal_lobby = {}
ranked_lobby = {}
active_games = {}
user_stats = {}

PLAYER_COLORS = [discord.Color.blue(), discord.Color.red()]
TEST_COLOR = discord.Color.green()

# --- [기능 함수들] ---
def apply_initial_sound_law(char):
    """ 두음 법칙 적용 함수 """
    if not char: return char
    code = ord(char) - 0xAC00
    if code < 0 or code > 11171: return char
    tail = code % 28
    vowel = (code // 28) % 21
    lead = (code // 28) // 21
    if lead == 5 and vowel in [0, 11, 13, 18]: lead = 2
    elif lead == 5 and vowel in [2, 4, 12, 14, 20]: lead = 11
    elif lead == 2 and vowel in [4, 12, 14, 20]: lead = 11
    else: return char
    return chr((lead * 21 + vowel) * 28 + tail + 0xAC00)

def check_next_words_available(char, used_words):
    """ 다음 이을 단어가 있는지 체크 """
    if not char: return False
    law_char = apply_initial_sound_law(char)
    available = [w for w in WORD_DICT if (w.startswith(char) or w.startswith(law_char)) and w not in used_words]
    return len(available) > 0

def is_killing_word(word, used_words):
    """ 한방 단어인지 체크 """
    if not word: return True
    last_char = word[-1]
    return not check_next_words_available(last_char, used_words)

def update_stats(winner, loser):
    """ 전적 업데이트 """
    for user in [winner, loser]:
        if user.id not in user_stats:
            user_stats[user.id] = {"name": user.display_name, "승": 0, "패": 0}
        user_stats[user.id]["name"] = user.display_name
        
    user_stats[winner.id]["승"] += 1
    user_stats[loser.id]["패"] += 1

def calculate_win_rate(win, lose):
    """ 승률 계산 함수 """
    total = win + lose
    if total == 0: return 0.0
    return round((win / total) * 100, 1)

@bot.event
async def on_ready():
    print(f"🤖 봇이 로그인했습니다: {bot.user.name}")

# 4. 명령어 처리: 1시작 / 1랭겜 / 1테스트 / 1취소(★추가됨)
@bot.command(name="1시작")
async def start_normal(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_games:
        await ctx.send("❌ 이 채널에서는 이미 다른 게임이 진행 중입니다!")
        return
    if ranked_lobby.get(channel_id) == ctx.author:
        await ctx.send("❌ 이미 `1랭겜` 신청을 해두셨습니다.")
        return
    if normal_lobby.get(channel_id) is None:
        normal_lobby[channel_id] = ctx.author
        await ctx.send(f"🎮 **[일반 게임]** {ctx.author.mention}님이 대전을 신청했습니다! 같이 하실 분은 대화창에 `1시작`을 쳐주세요.")
    else:
        if normal_lobby[channel_id] == ctx.author:
            await ctx.send("❌ 이미 대전 신청을 하셨습니다.")
            return
        p1 = normal_lobby[channel_id]
        p2 = ctx.author
        del normal_lobby[channel_id]
        await start_game_session(ctx, channel_id, p1, p2, ranked=False)

@bot.command(name="1랭겜")
async def start_ranked(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_games:
        await ctx.send("❌ 이 채널에서는 이미 다른 게임이 진행 중입니다!")
        return
    if normal_lobby.get(channel_id) == ctx.author:
        await ctx.send("❌ 이미 `1시작` 신청을 해두셨습니다.")
        return
    if ranked_lobby.get(channel_id) is None:
        ranked_lobby[channel_id] = ctx.author
        await ctx.send(f"🏆 **[랭킹 게임]** {ctx.author.mention}님이 대전을 신청했습니다! 같이 하실 분은 대화창에 `1랭겜`을 쳐주세요.")
    else:
        if ranked_lobby[channel_id] == ctx.author:
            await ctx.send("❌ 이미 대전 신청을 하셨습니다.")
            return
        p1 = ranked_lobby[channel_id]
        p2 = ctx.author
        del ranked_lobby[channel_id]
        await start_game_session(ctx, channel_id, p1, p2, ranked=True)

@bot.command(name="1취소")
async def cancel_lobby(ctx):
    channel_id = ctx.channel.id
    
    # 해당 채널에 일반겜이나 랭겜을 신청한 사람이 있는지 확인
    has_normal = normal_lobby.get(channel_id)
    has_ranked = ranked_lobby.get(channel_id)
    
    if not has_normal and not has_ranked:
        await ctx.send("❌ 현재 이 채널에 대기 중인 매칭 신청이 없습니다.")
        return
        
    # 신청한 본인만 취소할 수 있도록 체크
    if (has_normal == ctx.author) or (has_ranked == ctx.author):
        if has_normal:
            del normal_lobby[channel_id]
            await ctx.send(f"🛑 {ctx.author.mention}님이 **[일반 게임]** 매칭 신청을 취소하셨습니다.")
        elif has_ranked:
            del ranked_lobby[channel_id]
            await ctx.send(f"🛑 {ctx.author.mention}님이 **[랭킹 게임]** 매칭 신청을 취소하셨습니다.")
    else:
        await ctx.send("❌ 매칭 취소는 처음 대전을 신청한 본인만 할 수 있습니다!")

async def start_game_session(ctx, channel_id, p1, p2, ranked):
    active_games[channel_id] = {
        "mode": "ranked" if ranked else "normal",
        "players": [p1, p2],
        "current_turn": 0,
        "used_words": [],
        "word_owners": [],
        "last_word": "",
        "stolen": False
    }
    embed = discord.Embed(
        title="⚔️ 매칭 완료! 게임을 시작합니다.",
        description=f"**모드:** {'🏆 랭킹 게임 (무르기 불가)' if ranked else '🎮 일반 게임'}\n"
                    f"**블록 색상 및 괄호 안내:** \n"
                    f" 선공: {p1.mention} (🟦 파랑색 | 소괄호 `(단어)`)\n"
                    f" 후공: {p2.mention} (🟥 빨강색 | 대괄호 `[단어]`)\n\n"
                    f"⏱️ 첫 번째 차례: {p1.mention}님! 단어를 입력하세요.\n"
                    f"💡 *규칙: 선공이 첫 단어를 내면, 후공은 자기 턴(2번째 단어째)에 `1뺏기`로 그 단어를 빼앗아 올 수 있습니다!*",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="1테스트")
async def start_test(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_games:
        await ctx.send("❌ 이 채널에서는 이미 다른 게임이 진행 중입니다!")
        return
    
    if normal_lobby.get(channel_id) == ctx.author: del normal_lobby[channel_id]
    if ranked_lobby.get(channel_id) == ctx.author: del ranked_lobby[channel_id]

    active_games[channel_id] = {
        "mode": "test",
        "players": [ctx.author],
        "current_turn": 0,
        "used_words": [],
        "word_owners": [],
        "last_word": "",
        "stolen": False
    }
    
    embed = discord.Embed(
        title="🧪 혼자 하기 (연습 모드) 시작",
        description=f"혼자서 단어를 자유롭게 입력하며 테스트해볼 수 있습니다.\n"
                    f"종료하려면 단어가 막히거나 `1기권`을 입력하세요.\n\n"
                    f"⏱️ {ctx.author.mention}님! 첫 단어를 입력해 주세요.",
        color=TEST_COLOR
    )
    await ctx.send(embed=embed)

# 5. 특수 명령어 처리: 1무르기 / 1기권 / 1뺏기 / 1전적 / 1랭킹 / 1명령어 / 1전적초기화
@bot.command(name="1명령어")
async def show_help(ctx):
    embed = discord.Embed(
        title="📚 끝말잇기 봇 설명서",
        description="봇과 함께 즐길 수 있는 전체 명령어와 규칙 안내입니다.",
        color=discord.Color.purple()
    )
    embed.add_field(name="🎮 게임 시작 명령어", value="`1시작` : 일반 끝말잇기 게임을 신청하거나 참가합니다.\n`1랭겜` : 승/패 기록이 남는 랭킹 게임을 신청하거나 참가합니다.\n`1테스트` : 혼자서 단어를 이어가며 연습하는 방을 만듭니다.\n`1취소` : 상대가 오기 전 대기 중인 내 매칭 신청을 취소합니다.", inline=False)
    embed.add_field(name="⚡ 게임 중 특수 명령어", value="`1무르기 [단어]` : **[일반 전용]** 내가 냈던 단어를 지정해 그 시점으로 롤백합니다.\n`1뺏기` : **[후공 전용]** 선공이 첫 단어를 냈을 때 후공이 그 단어의 주도권을 빼앗아옵니다.\n`1기권` : 진행 중인 게임을 포기합니다. (랭겜은 기권 시 패배 기록)", inline=False)
    embed.add_field(name="📊 전적 및 순위 확인", value="`1전적` : 본인의 개인 승, 패, 승률을 확인합니다.\n`1랭킹` : 서버 전체 유저들의 통합 순위표를 출력합니다.", inline=False)
    embed.add_field(name="👑 관리자(소유자) 전용", value="`1전적초기화` : 데이터베이스에 누적된 전체 유저의 랭킹 전적을 모두 삭제합니다.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="1전적초기화")
@commands.is_owner()
async def reset_all_stats(ctx):
    global user_stats
    user_stats.clear()
    await ctx.send("🧹 **[시스템 안내]** 봇 소유자의 권한으로 서버 전체 유저의 랭킹 전적이 모두 초기화되었습니다!")

@reset_all_stats.error
async def reset_all_stats_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("❌ **[권한 거부]** 이 명령어는 봇 소유자(Owner)만 사용할 수 있습니다!")

@bot.command(name="1무르기")
async def undo_word(ctx, word: str = None):
    channel_id = ctx.channel.id
    if channel_id not in active_games: return
    game = active_games[channel_id]
    if game["mode"] == "ranked":
        await ctx.send("❌ 랭킹 게임에서는 무르기를 사용할 수 없습니다!")
        return
    if word is None:
        await ctx.send("❌ 무를 단어를 함께 입력해주세요! (예: `1무르기 사과`)")
        return
    if word not in game["used_words"]:
        await ctx.send(f"❌ 이번 게임에서 `{word}` 단어는 사용된 적이 없습니다!")
        return
    word_index = game["used_words"].index(word)
    
    if game["mode"] != "test" and game["word_owners"][word_index] != ctx.author:
        await ctx.send(f"❌ `{word}` 단어는 상대방이 낸 단어입니다! 본인이 친 단어만 무를 수 있습니다.")
        return

    game["used_words"] = game["used_words"][:word_index]
    game["word_owners"] = game["word_owners"][:word_index]
    game["last_word"] = game["used_words"][-1] if game["used_words"] else ""
    game["current_turn"] = 0 if game["mode"] == "test" else game["players"].index(ctx.author)

    hint = "첫 턴입니다. 자유롭게 입력하세요."
    if game["last_word"]:
        next_char = game["last_word"][-1]
        law_char = apply_initial_sound_law(next_char)
        hint = f"제시어: `{next_char}`" if next_char == law_char else f"제시어: `{next_char}` (또는 `{law_char}`)"
    await ctx.send(f"🔄 **타임머신 무르기 적용!** `{word}` 단어가 입력되기 전 상태로 되돌립니다. 다시 {ctx.author.mention}님 차례입니다! ({hint})")

@bot.command(name="1기권")
async def forfeit_game(ctx):
    channel_id = ctx.channel.id
    if channel_id not in active_games: return
    game = active_games[channel_id]
    if ctx.author not in game["players"]: return

    if game["mode"] == "test":
        await ctx.send(f"🏳️ {ctx.author.mention}님이 연습 모드를 종료하셨습니다.")
    elif game["mode"] == "ranked":
        loser = ctx.author
        winner = game["players"][1] if game["players"][0] == loser else game["players"][0]
        update_stats(winner, loser)
        w_stat = user_stats[winner.id]
        l_stat = user_stats[loser.id]
        w_rate = calculate_win_rate(w_stat["승"], w_stat["패"])
        l_rate = calculate_win_rate(l_stat["승"], l_stat["패"])
        await ctx.send(f"🏳️ {loser.mention}님이 기권하셨습니다. **[랭킹 전적 반영]**\n"
                       f"🏆 승리: {winner.mention} ({w_stat['승']}승 {w_stat['패']}패 | 승률: {w_rate}%)\n"
                       f"💀 패배: {loser.mention} ({l_stat['승']}승 {l_stat['패']}패 | 승률: {l_rate}%)")
    else:
        await ctx.send(f"🏳️ {ctx.author.mention}님이 기권하여 게임이 종료되었습니다. (일반 게임)")
    del active_games[channel_id]

@bot.command(name="1뺏기")
async def steal_turn(ctx):
    channel_id = ctx.channel.id
    if channel_id not in active_games: return
    game = active_games[channel_id]
    
    if game["mode"] == "test": return
    
    if ctx.author != game["players"][1]:
        await ctx.send("❌ 선공 권한을 가로챌 수 없습니다! 뺏기는 오직 후공 유저만 사용할 수 있습니다.")
        return
        
    if len(game["used_words"]) == 0:
        await ctx.send("❌ 선공이 아직 단어를 입력하지 않았습니다! 선공이 첫 단어를 낸 후에만 뺏을 수 있습니다.")
        return
    elif len(game["used_words"]) != 1:
        await ctx.send("❌ 타이밍이 지났습니다! 뺏기는 전체 기보의 2번째 순서(첫 턴)에만 사용할 수 있습니다.")
        return

    stolen_word = game["used_words"][0]
    game["word_owners"][0] = ctx.author  
    game["stolen"] = True
    game["current_turn"] = 0  
    
    history_chain = f"**`[{stolen_word}]`**"
    
    embed = discord.Embed(
        title="💥 뺏기 발동! 주도권이 역전되었습니다.",
        description=f"후공 {ctx.author.mention}님이 선공의 첫 단어를 빼앗아 가셨습니다!\n\n"
                    f"현재 기보: {history_chain}",
        color=discord.Color.orange()
    )
    
    next_char = stolen_word[-1]
    law_next_char = apply_initial_sound_law(next_char)
    hint_text = f"`{next_char}`" if next_char == law_next_char else f"`{next_char}` (또는 `{law_next_char}`)"
    
    p1 = game["players"][0]
    mention_text = f"⚔️ 첫 단어를 빼앗긴 {p1.mention}님 차례입니다! 제시어 {hint_text}에 맞춰 다시 단어를 이어 나가세요."
    
    await ctx.send(embed=embed)
    await ctx.send(mention_text)

@bot.command(name="1전적")
async def show_stats(ctx):
    user = ctx.author
    if user.id not in user_stats:
        await ctx.send(f"📊 {user.mention}님은 아직 랭킹전 전적이 없습니다.")
    else:
        stat = user_stats[user.id]
        win_rate = calculate_win_rate(stat["승"], stat["패"])
        await ctx.send(f"📊 **{user.display_name}님의 랭킹 전적:** {stat['승']}승 {stat['패']}패 (승률: {win_rate}%)")

@bot.command(name="1랭킹")
async def show_leaderboard(ctx):
    if not user_stats:
        await ctx.send("📊 아직 랭킹 게임 전적이 등록된 유저가 없습니다!")
        return

    sorted_stats = sorted(
        user_stats.values(),
        key=lambda x: (x["승"], calculate_win_rate(x["승"], x["패"])),
        reverse=True
    )

    embed = discord.Embed(
        title="🏆 통합 랭킹 순위표",
        description="서버 전체 플레이어들의 끝말잇기 랭킹 순위입니다.",
        color=discord.Color.gold()
    )

    ranking_text = ""
    for idx, stat in enumerate(sorted_stats, start=1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`{idx}위`"
        win_rate = calculate_win_rate(stat["승"], stat["패"])
        ranking_text += f"{medal} **{stat['name']}** - {stat['승']}승 {stat['패']}패 (승률: {win_rate}%)\n"

    embed.add_field(name="✨ 현재 순위 리스트", value=ranking_text, inline=False)
    await ctx.send(embed=embed)

# 6. 게임 진행 채팅 감지
@bot.event
async def on_message(message):
    if message.author.bot: return
    channel_id = message.channel.id
    msg_content = message.content.strip()
    
    # 1취소 명령어도 바이패스 리스트에 포함
    if msg_content in ["1시작", "1랭겜", "1테스트", "1기권", "1뺏기", "1전적", "1랭킹", "1명령어", "1전적초기화", "1취소"] or msg_content.startswith("1무르기"):
        await bot.process_commands(message)
        return

    if channel_id in active_games:
        game = active_games[channel_id]
        
        is_my_turn = False
        if game["mode"] == "test" and message.author == game["players"][0]:
            is_my_turn = True
        elif game["mode"] != "test" and message.author == game["players"][game["current_turn"]]:
            is_my_turn = True

        if is_my_turn:
            word = msg_content
            
            if not word: return
            
            if word not in WORD_DICT:
                return
                
            if word in game["used_words"]:
                await message.reply("❌ 이미 사용된 단어입니다!")
                return
            if len(game["used_words"]) == 0 and is_killing_word(word, game["used_words"]):
                await message.reply("⚠️ 첫 턴에는 다음에 이을 수 없는 '한방 단어'를 사용할 수 없습니다!")
                return
            if game["last_word"]:
                required_char = game["last_word"][-1]
                allowed_law_char = apply_initial_sound_law(required_char)
                if word[0] != required_char and word[0] != allowed_law_char:
                    await message.reply(f"❌ '{required_char}' 또는 '{allowed_law_char}'(으)로 시작해야 합니다!")
                    return

            # 단어 등록
            game["used_words"].append(word)
            game["word_owners"].append(message.author)
            game["last_word"] = word
            
            history_list = []
            for owner, w in zip(game["word_owners"], game["used_words"]):
                if game["mode"] == "test":
                    history_list.append(f"**`({w})`**")
                else:
                    if owner == game["players"][0]:
                        history_list.append(f"**`({w})`**") 
                    else:
                        history_list.append(f"**`[{w}]`**") 
                        
            history_chain = " ➔ ".join(history_list)
            
            embed = discord.Embed(
                title="📝 현재 경기 전체 기보 " + ("(🧪 연습 모드)" if game["mode"] == "test" else ""),
                description=history_chain,
                color=TEST_COLOR if game["mode"] == "test" else PLAYER_COLORS[game["current_turn"]]
            )

            # 종료 체크
            next_char = word[-1]
            if not check_next_words_available(next_char, game["used_words"]):
                law_next_char = apply_initial_sound_law(next_char)
                display_char = next_char if next_char == law_next_char else f"{next_char}/{law_next_char}"
                
                await message.channel.send(embed=embed)
                
                if game["mode"] == "test":
                    await message.channel.send(f"🛑 **[연습 종료]** 더 이상 '{display_char}'(으)로 시작하는 단어가 단어장에 없습니다. 고생하셨습니다!")
                else:
                    winner = game["players"][game["current_turn"]]
                    loser = game["players"][1 - game["current_turn"]]
                    result_msg = f"🛑 **[스택]** 더 이상 '{display_char}'(으)로 시작하는 단어가 단어장에 없습니다!\n"
                    if game["mode"] == "ranked":
                        update_stats(winner, loser)
                        w_stat = user_stats[winner.id]
                        l_stat = user_stats[loser.id]
                        w_rate = calculate_win_rate(w_stat["승"], w_stat["패"])
                        l_rate = calculate_win_rate(l_stat["승"], l_stat["패"])
                        result_msg += f"🏆 {winner.mention}님의 승리! **[랭킹 전적 반영]**\n" \
                                      f"🥇 승리자 전적: {w_stat['승']}승 {w_stat['패']}패 (승률: {w_rate}%)\n" \
                                      f"💀 패배자 전적: {l_stat['승']}승 {l_stat['패']}패 (승률: {l_rate}%)"
                    else:
                        result_msg += f"🏆 {winner.mention}님의 승리로 게임이 종료되었습니다! (일반 게임)"
                    await message.channel.send(result_msg)
                
                del active_games[channel_id]
                return

            # 다음 턴 안내 처리
            law_next_char = apply_initial_sound_law(next_char)
            hint_text = f"`{next_char}`" if next_char == law_next_char else f"`{next_char}` (또는 `{law_next_char}`)"
            
            if game["mode"] == "test":
                mention_text = f"✅ 입력 완료! ➔ ⏱️ 다음 제시어: {hint_text} (혼자 계속 입력하세요)"
            else:
                next_turn_idx = 1 - game["current_turn"]
                game["current_turn"] = next_turn_idx
                p_current = message.author
                p_next = game["players"][next_turn_idx]
                
                if len(game["used_words"]) == 1 and not game["stolen"]:
                    mention_text = f"✅ {p_current.mention}님 입력 완료! ➔ ⏱️ 다음 차례: {p_next.mention}님 (제시어: {hint_text})\n💡 *{p_next.display_name}님은 단어를 치는 대신 `1뺏기`를 입력해 선공의 첫 단어를 뺏어올 수 있습니다!*"
                else:
                    mention_text = f"✅ {p_current.mention}님 입력 완료! ➔ ⏱️ 다음 차례: {p_next.mention}님 (제시어: {hint_text})"
            
            await message.channel.send(embed=embed)
            await message.channel.send(mention_text)

    await bot.process_commands(message)


# 6. 토큰 넣기 (본인의 봇 토큰으로 교체하세요)
bot.run('MTUyNjEwNTU4NDg2NzIxMzQ2NA.GcORK7.KgU9JOsBZlb5_Yq3rSTaetuxTu6x09w0kKDJAQ')
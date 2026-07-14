import discord
from discord.ext import commands
import os
import sys
import traceback
import json

# 1. 인텐트 및 봇 설정
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="", intents=intents)

WORD_DICT = []
FILE_NAME = "words.txt"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, FILE_NAME)

# 단어장 파일 로드 (인코딩 안전 장치 포함)
if os.path.exists(FILE_PATH):
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            WORD_DICT = [w.strip() for w in f.read().split() if w.strip()]
    except Exception as e:
        try:
            with open(FILE_PATH, "r", encoding="utf-8-sig") as f:
                WORD_DICT = [w.strip() for w in f.read().split() if w.strip()]
        except Exception as e2:
            with open(FILE_PATH, "r", encoding="cp949") as f:
                WORD_DICT = [w.strip() for w in f.read().split() if w.strip()]
            
    print(f"✅ 단어장 파일 로드 완료! 위치: {FILE_PATH}")
    print(f"📊 총 {len(WORD_DICT)}개의 단어가 등록되었습니다.")
else:
    print(f"⚠️ 경고: {FILE_NAME} 파일이 없습니다!")

# 전역 변수 및 데이터 구조
normal_lobby = {}
ranked_lobby = {}
active_games = {}
user_stats = {}

STATS_FILE = "user_stats.json"

# 전적 데이터 로드
if os.path.exists(STATS_FILE):
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            user_stats = json.load(f)
            # JSON의 키(문자열)를 다시 정수형 ID로 변환
            user_stats = {int(k): v for k, v in user_stats.items()}
    except Exception as e:
        print(f"⚠️ 전적 로드 실패: {e}")

def save_stats():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            # dict 키를 문자열로 변환하여 저장 (JSON 규격 맞춤)
            save_data = {str(k): v for k, v in user_stats.items()}
            json.dump(save_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ 전적 저장 실패: {e}")

PLAYER_COLORS = [discord.Color.blue(), discord.Color.red()]
TEST_COLOR = discord.Color.green()

# 🎯 종성(받침)에 상관없이 초성과 중성(모음)을 표준 규격대로 분석하는 두음 법칙 함수
def apply_initial_sound_law(char):
    if not char: return char
    
    code = ord(char) - 0xAC00
    if code < 0 or code > 11171: return char
    
    # 한글 유니코드 분해 (초성, 중성, 종성)
    tail = code % 28          # 종성 (받침)
    vowel = (code // 28) % 21 # 중성 (모음)
    lead = (code // 28) // 21  # 초성 (자음)
    
    # 1. 초성이 'ㄹ'(lead == 5)인 경우 처리
    if lead == 5:
        # 'ㅐ' 모음(vowel == 1) -> 초성을 'ㄴ'(lead = 2)으로 변경 (예: 랙 -> 낵, 랭 -> 냉)
        if vowel == 1:
            lead = 2
        # 'ㅖ' 모음(vowel == 7) -> 초성을 'ㅇ'(lead = 11)으로 변경 (예: 례 -> 예, 롄 -> 옌)
        elif vowel == 7:
            lead = 11
            
        # 기존 유니코드 표준 두음 법칙 규칙들
        elif vowel == 11: # 'ㅚ' 모음은 그대로 유지
            pass 
        elif vowel in [0, 4, 8, 13]: # ㅏ(0), ㅓ(4), ㅗ(8), ㅜ(13) -> 'ㄴ'(2)으로 변경 (예: 란 -> 난, 롬 -> 놈)
            lead = 2
        elif vowel in [2, 6, 12, 17, 20]: # ㅑ(2), ㅕ(6), ㅛ(12), ㅠ(17), ㅣ(20) -> 'ㅇ'(11)으로 변경 (예: 린 -> 인, 룡 -> 용)
            lead = 11
            
    # 2. 초성이 'ㄴ'(lead == 2)인 경우 처리
    elif lead == 2:
        if vowel in [6, 12, 17, 20]: # 녀(6), 뇨(12), 뉴(17), 니(20) -> 'ㅇ'(11)으로 변경 (예: 뇨 -> 요)
            lead = 11
            
    else:
        return char
        
    # 변경된 초성, 중성, 종성을 다시 하나의 글자로 조합하여 반환
    return chr((lead * 21 + vowel) * 28 + tail + 0xAC00)

def check_next_words_available(char, used_words):
    if not char: return False
    law_char = apply_initial_sound_law(char)
    available = [w for w in WORD_DICT if (w.startswith(char) or w.startswith(law_char)) and w not in used_words]
    return len(available) > 0

def is_killing_word(word, used_words):
    if not word: return True
    last_char = word[-1]
    return not check_next_words_available(last_char, used_words)

def update_stats(winner, loser, is_ranked=False):
    for user in [winner, loser]:
        if user.id not in user_stats:
            user_stats[user.id] = {
                "name": user.display_name,
                "승": 0, "패": 0, "레이팅": 1000,
                "일반승": 0, "일반패": 0,
                "랭킹승": 0, "랭킹패": 0
            }
        user_stats[user.id]["name"] = user.display_name

    if is_ranked:
        # 레이팅 변동 공식 적용
        r_winner = user_stats[winner.id]["레이팅"]
        r_loser = user_stats[loser.id]["레이팅"]
        
        # 기댓값 계산
        exp_winner = 1 / (1 + 10 ** ((r_loser - r_winner) / 400))
        exp_loser = 1 - exp_winner
        
        # 변동 폭 상수 K=32
        k_factor = 32
        new_r_winner = round(r_winner + k_factor * (1 - exp_winner))
        new_r_loser = round(r_loser + k_factor * (0 - exp_loser))
        
        # 변동폭이 최소 10은 되도록 보정
        diff_winner = max(10, new_r_winner - r_winner)
        diff_loser = min(-10, new_r_loser - r_loser)
        
        user_stats[winner.id]["레이팅"] += diff_winner
        user_stats[loser.id]["레이팅"] += diff_loser
        
        user_stats[winner.id]["승"] += 1
        user_stats[winner.id]["랭킹승"] += 1
        user_stats[loser.id]["패"] += 1
        user_stats[loser.id]["랭킹패"] += 1
        
        save_stats()
        return diff_winner, diff_l_loser if 'diff_l_loser' in locals() else diff_loser
    else:
        user_stats[winner.id]["승"] += 1
        user_stats[winner.id]["일반승"] += 1
        user_stats[loser.id]["패"] += 1
        user_stats[loser.id]["일반패"] += 1
        save_stats()
        return 0, 0

def calculate_win_rate(win, lose):
    total = win + lose
    if total == 0: return 0.0
    return round((win / total) * 100, 1)

@bot.event
async def on_ready():
    print("---------------------------------------")
    print(f"🤖 봇이 완전히 로그인했습니다: {bot.user.name}")
    print("---------------------------------------")

# 전역 예외 처리 (에러 로깅용)
@bot.event
async def on_error(event, *args, **kwargs):
    print(f"❌ 에러 발생 (Event: {event})", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)

@bot.command(name="1시작")
async def start_normal(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_games: return
    if normal_lobby.get(channel_id) is None:
        normal_lobby[channel_id] = ctx.author
        await ctx.send(f"🎮 **[일반 게임]** {ctx.author.mention}님이 대전을 신청했습니다! `1시작`을 쳐서 참가하세요.")
    else:
        if normal_lobby[channel_id] == ctx.author: return
        p1 = normal_lobby[channel_id]
        p2 = ctx.author
        del normal_lobby[channel_id]
        await start_game_session(ctx, channel_id, p1, p2, ranked=False)

@bot.command(name="1랭겜")
async def start_ranked(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_games: return
    if ranked_lobby.get(channel_id) is None:
        ranked_lobby[channel_id] = ctx.author
        await ctx.send(f"🏆 **[랭킹 게임]** {ctx.author.mention}님이 대전을 신청했습니다! `1랭겜`을 쳐서 참가하세요.")
    else:
        if ranked_lobby[channel_id] == ctx.author: return
        p1 = ranked_lobby[channel_id]
        p2 = ctx.author
        del ranked_lobby[channel_id]
        await start_game_session(ctx, channel_id, p1, p2, ranked=True)

@bot.command(name="1취소")
async def cancel_lobby(ctx):
    channel_id = ctx.channel.id
    has_normal = normal_lobby.get(channel_id)
    has_ranked = ranked_lobby.get(channel_id)
    if not has_normal and not has_ranked: return
    if has_normal == ctx.author:
        del normal_lobby[channel_id]
        await ctx.send(f"🛑 일반 게임 매칭을 취소했습니다.")
    elif has_ranked == ctx.author:
        del ranked_lobby[channel_id]
        await ctx.send(f"🛑 랭킹 게임 매칭을 취소했습니다.")

async def start_game_session(ctx, channel_id, p1, p2, ranked):
    active_games[channel_id] = {
        "mode": "ranked" if ranked else "normal",
        "players": [p1, p2],
        "current_turn": 0,
        "used_words": [],
        "word_owners": [],
        "last_word": "",
        "stolen": False,
        "history": [] # 무르기용 히스토리 기록 백업
    }
    mode_str = "🏆 랭킹 게임" if ranked else "🎮 일반 게임"
    embed = discord.Embed(
        title=f"⚔️ {mode_str} 매칭 완료!",
        description=f"선공: {p1.mention} / 후공: {p2.mention}\n⏱️ 첫 번째 차례: {p1.mention}님!",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="1명령어")
async def show_help(ctx):
    embed = discord.Embed(
        title="📚 끝말잇기 설명서", 
        description="`1시작` : 일반전 대기열 등록 / 참가\n`1랭겜` : 랭킹전 대기열 등록 / 참가\n`1취소` : 등록된 대기열 취소\n`1기권` : 게임 중 기권하고 패배 처리\n`1뺏기` : 선공의 첫 단어를 뺏어 내 차례로 만듦\n`1무르기` : 이전 턴으로 한 단계 되돌리기\n`1전적` : 본인의 통합 및 모드별 전적 보기\n`1랭킹` : 레이팅 점수 기준 탑 10 랭킹 출력", 
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

@bot.command(name="1기권")
async def forfeit_game(ctx):
    channel_id = ctx.channel.id
    if channel_id not in active_games: return
    game = active_games[channel_id]
    if ctx.author not in game["players"]: return
    
    loser = ctx.author
    winner = game["players"][1] if loser == game["players"][0] else game["players"][0]
    
    is_ranked = (game["mode"] == "ranked")
    
    await ctx.send(f"🏳️ {loser.mention}님이 기권을 선언했습니다.")
    
    if is_ranked:
        diff_w, diff_l = update_stats(winner, loser, is_ranked=True)
        embed = discord.Embed(title="🏆 게임 종료 (랭킹전)", color=discord.Color.red())
        embed.add_field(name="승리", value=f"{winner.mention} (+{diff_w}p ➔ {user_stats[winner.id]['레이팅']}p)", inline=False)
        embed.add_field(name="패배 (기권)", value=f"{loser.mention} ({diff_l}p ➔ {user_stats[loser.id]['레이팅']}p)", inline=False)
        await ctx.send(embed=embed)
    else:
        update_stats(winner, loser, is_ranked=False)
        await ctx.send(f"🎉 {winner.mention}님이 일반 게임에서 승리하셨습니다!")
        
    del active_games[channel_id]

@bot.command(name="1뺏기")
async def steal_turn(ctx):
    channel_id = ctx.channel.id
    if channel_id not in active_games: return
    game = active_games[channel_id]
    
    # 후공이면서, 첫 단어만 입력된 타이밍이고, 아직 뺏기를 쓴 적이 없을 때만 가능
    if ctx.author != game["players"][1]: return
    if len(game["used_words"]) != 1: return
    if game["stolen"]: return
    
    # 히스토리에 백업 (무르기 대비)
    game["history"].append({
        "used_words": list(game["used_words"]),
        "word_owners": list(game["word_owners"]),
        "last_word": game["last_word"],
        "current_turn": game["current_turn"],
        "stolen": False
    })
    
    game["word_owners"][0] = ctx.author  
    game["stolen"] = True
    game["current_turn"] = 0  
    await ctx.send(f"💥 {ctx.author.mention}님이 선공의 첫 단어를 빼앗아 내 단어로 만들었습니다! 다음 제시어는 그대로 `{game['last_word'][-1]}` 입니다.")

@bot.command(name="1무르기")
async def undo_turn(ctx):
    channel_id = ctx.channel.id
    if channel_id not in active_games: return
    game = active_games[channel_id]
    
    if ctx.author not in game["players"]: return
    if not game["history"]:
        await ctx.send("⏮️ 더 이상 되돌릴 이전 기록이 없습니다!")
        return
        
    # 바로 직전의 세션 상태로 완전 복원
    last_state = game["history"].pop()
    game["used_words"] = last_state["used_words"]
    game["word_owners"] = last_state["word_owners"]
    game["last_word"] = last_state["last_word"]
    game["current_turn"] = last_state["current_turn"]
    game["stolen"] = last_state["stolen"]
    
    if game["last_word"]:
        await ctx.send(f"⏮️ 직전 차례로 무르기가 성공했습니다! 제시어: `{game['last_word'][-1]}` ➔ 차례: {game['players'][game['current_turn']].mention}")
    else:
        await ctx.send(f"⏮️ 게임이 첫 시작 상태로 되돌아왔습니다! 선공: {game['players'][0].mention}님 단어를 입력해 주세요.")

@bot.command(name="1전적")
async def show_stats(ctx):
    user_id = ctx.author.id
    if user_id not in user_stats:
        await ctx.send("📊 아직 플레이하신 기록이 없습니다.")
    else:
        s = user_stats[user_id]
        total_games = s["승"] + s["패"]
        win_rate = calculate_win_rate(s["승"], s["패"])
        
        embed = discord.Embed(title=f"📊 {s['name']}님의 전적", color=discord.Color.blue())
        embed.add_field(name="🏆 랭킹 레이팅", value=f"**{s['레이팅']} 점**", inline=False)
        embed.add_field(name="⚔️ 통합 전적", value=f"{total_games}전 {s['승']}승 {s['패']}패 (승률: {win_rate}%)", inline=False)
        embed.add_field(name="🎮 일반 모드", value=f"{s.get('일반승', 0)}승 {s.get('일반패', 0)}패", inline=True)
        embed.add_field(name="🏆 랭킹 모드", value=f"{s.get('랭킹승', 0)}승 {s.get('랭킹패', 0)}패", inline=True)
        await ctx.send(embed=embed)

@bot.command(name="1랭킹")
async def show_leaderboard(ctx):
    if not user_stats:
        await ctx.send("📊 등록된 랭킹 데이터가 없습니다.")
        return
        
    # 레이팅 기준으로 내림차순 정렬
    sorted_players = sorted(user_stats.items(), key=lambda x: x[1]["레이팅"], reverse=True)[:10]
    
    embed = discord.Embed(title="🏆 실시간 레이팅 탑 10 랭킹", color=discord.Color.gold())
    
    rank_list = ""
    for idx, (p_id, s) in enumerate(sorted_players, start=1):
        win_rate = calculate_win_rate(s["승"], s["패"])
        rank_list += f"**{idx}위** | {s['name']} - **{s['레이팅']}p** ({s['승']}승 {s['패']}패, {win_rate}%)\n"
        
    embed.description = rank_list
    await ctx.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author.bot: return
    channel_id = message.channel.id
    msg_content = message.content.strip()
    
    # 봇 명령어 필터링
    if msg_content in ["1시작", "1랭겜", "1기권", "1뺏기", "1전적", "1랭킹", "1명령어", "1취소"] or msg_content.startswith("1무르기"):
        await bot.process_commands(message)
        return

    if channel_id in active_games:
        game = active_games[channel_id]
        
        # 현재 내 턴이 맞는지 확인
        if message.author == game["players"][game["current_turn"]]:
            word = msg_content
            
            # [수정] 단어 규칙 검증 및 사용자 알림 추가
            if word not in WORD_DICT:
                await message.channel.send(f"❌ `{word}`은(는) 단어 사전에 존재하지 않는 단어입니다!")
                return
            if word in game["used_words"]:
                await message.channel.send(f"❌ `{word}`은(는) 이미 사용된 단어입니다!")
                return
            
            # 첫 턴 한정 한방 단어(킬링워드) 필터링 방어막
            if len(game["used_words"]) == 0 and is_killing_word(word, game["used_words"]):
                await message.channel.send("⚠️ 첫 단어로 상대를 바로 끝내는 한방 단어(킬링워드)는 사용할 수 없습니다! 다른 단어를 입력해 주세요.")
                return
                
            # 끝말이 이어지는지 검사 (두음 법칙 적용)
            if game["last_word"]:
                req = game["last_word"][-1]
                req_law = apply_initial_sound_law(req)
                if word[0] != req and word[0] != req_law:
                    await message.channel.send(f"❌ 제시어 맞춤법 오류! `{req}`(또는 두음법칙 `{req_law}`) (으)로 시작하는 단어여야 합니다.")
                    return

            # 성공적인 턴 실행 - 히스토리에 현 세션 백업
            game["history"].append({
                "used_words": list(game["used_words"]),
                "word_owners": list(game["word_owners"]),
                "last_word": game["last_word"],
                "current_turn": game["current_turn"],
                "stolen": game["stolen"]
            })

            game["used_words"].append(word)
            game["word_owners"].append(message.author)
            game["last_word"] = word
            
            next_char = word[-1]
            # 다음에 이어갈 수 있는 단어가 없는 경우 게임 끝
            if not check_next_words_available(next_char, game["used_words"]):
                winner = message.author
                loser = game["players"][1] if winner == game["players"][0] else game["players"][0]
                is_ranked = (game["mode"] == "ranked")
                
                await message.channel.send(f"🛑 끝! `{next_char}`(으)로 이어갈 단어가 사전에 없습니다.")
                
                if is_ranked:
                    diff_w, diff_l = update_stats(winner, loser, is_ranked=True)
                    embed = discord.Embed(title="🏆 게임 종료 (랭킹전)", color=discord.Color.gold())
                    embed.add_field(name="승리", value=f"{winner.mention} (+{diff_w}p ➔ {user_stats[winner.id]['레이팅']}p)", inline=False)
                    embed.add_field(name="패배", value=f"{loser.mention} ({diff_l}p ➔ {user_stats[loser.id]['레이팅']}p)", inline=False)
                    await message.channel.send(embed=embed)
                else:
                    update_stats(winner, loser, is_ranked=False)
                    await message.channel.send(f"🎉 {winner.mention}님이 일반 게임에서 승리하셨습니다!")
                    
                del active_games[channel_id]
                return
                
            # 턴 교대 및 출력
            game["current_turn"] = 1 - game["current_turn"]
            await message.channel.send(f"✅ 제시어: `{next_char}` ➔ 다음 차례: {game['players'][game['current_turn']].mention}")

    await bot.process_commands(message)

# 6. 토큰 넣기 (본인의 봇 토큰으로 교체하세요)
bot.run('MTUyNjEwNTU4NDg2NzIxMzQ2NA.GlNkoB.11DMpNkhkhcncHouPkHnD-PtIBcNf--D04pCwY')
#!/usr/bin/python
import json
from collections import defaultdict
import requests
from datetime import date, timedelta, datetime
import time
import logging
import os
import pytz
import operator
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

from config import espn_team_mapping as team_mapping

def capitalize_keys(d):
    upper_dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            v = capitalize_keys(v)
        upper_dict[k.upper()] = v
    return upper_dict

class Schedule(object):
    schedule_by_team = defaultdict(list)
    schedule_by_date = defaultdict(list)

    def __init__(self, season):
        with open(f"schedule-{season}.json") as f:
            self.schedule = json.load(f)

        for thing in self.schedule['lscd']:
            for game in thing['mscd']['g']:
                # logging.debug(f"considering {game['gcode']}")
                self.schedule_by_team[game['v']['ta']].append(game['gdte'])
                self.schedule_by_team[game['h']['ta']].append(game['gdte'])
                self.schedule_by_date[game['gdte']].append(game)
        # print(json.dumps(self.schedule_by_team))

    @classmethod
    def scoring_period(self, target_date):
        season_start = datetime.strptime('2018-10-16', '%Y-%m-%d')
        delta = datetime.strptime(target_date, '%Y-%m-%d') - season_start
        return delta.days + 1

    @classmethod
    def upcoming_players(self, p):
        game_window_start = datetime.today()
        game_window_end = datetime.today() + timedelta(days=4)
        player_matches = defaultdict(int)
        for k, player in p.players.items():
            for scheduled_game in self.schedule_by_team[player['TEAM_ABBREVIATION']]:
                scheduled_game_date = datetime.strptime(scheduled_game, '%Y-%m-%d')
                if scheduled_game_date >= game_window_start and scheduled_game_date < game_window_end:
                    if player['PLAYER_ID'] in player_matches:
                        player_matches[player['PLAYER_ID']] = player_matches[player['PLAYER_ID']] + 1
                    else:
                        player_matches[player['PLAYER_ID']] = 1
                    # print(f"player {player['PLAYER_NAME']} plays in next 3 days (on {scheduled_game_date})")

        for k, player in p.players.items():
            fantasy_score = p.calculate_fantasy_score(player)
            if player['MIN'] > 18.0 and fantasy_score > 30.0:
                pass
                # print(f"player {player['PLAYER_NAME']} has {player_matches[k]} games and plays {player['MIN']} minutes for {fantasy_score} we have {len(b.boxscores_by_player.get(player['PLAYER_NAME'], []))} game boxscores for him.")
                # print(f"{player}")


class Players(object):
    def __init__(self):
        # response = requests.get('https://stats.nba.com/stats/leaguedashplayerstats?College=&Conference=&Country=&DateFrom=&DateTo=&Division=&DraftPick=&DraftYear=&GameScope=&GameSegment=&Height=&LastNGames=0&LeagueID=00&Location=&MeasureType=Base&Month=0&OpponentTeamID=0&Outcome=&PORound=0&PaceAdjust=N&PerMode=PerGame&Period=0&PlayerExperience=&PlayerPosition=&PlusMinus=N&Rank=N&Season=2018-19&SeasonSegment=&SeasonType=Pre+Season&ShotClockRange=&StarterBench=&TeamID=0&VsConference=&VsDivision=&Weight=')
        response = None
        with open('players.json') as f:
            response = json.load(f)
        players = response['resultSets'][0]
        headers = players['headers']
        self.players = {}
        for player in players['rowSet']:
            player_data = {}
            for column in headers:
                player_data[column] = player.pop(0)
            self.players[player_data['PLAYER_ID']] = player_data
            # print(f"loaded {player_data['PLAYER_NAME']} playing for {player_data['TEAM_ABBREVIATION']}")
        # print(json.dumps(self.players))

    @classmethod
    def calculate_fantasy_score(self, player) -> float:
        double_stats = 0
        for stat in ['AST', 'STL', 'BLK', 'PTS']:
            if player[stat] >= 10:
                double_stats = double_stats + 1
        if player['OREB'] + player['DREB'] >= 10:
            double_stats = double_stats + 1
        if double_stats == 2:
            player['DD'] = 1
        if double_stats == 3:
            player['TD'] = 1
        if double_stats == 4:
            player['QD'] = 1
        score = 0.0
        score -= (player['FGA']  * 0.75)
        score += (player['FGM']  * 1.0)
        score += (player.get('FG3M', player.get('TPM', 0)) * 0.5)
        score -= (player['FTA']  * 0.5)
        score += (player['FTM']  * 1.0)
        score += (player['OREB']  * 1.5)
        score += (player['DREB']  * 0.5)
        score += (player['AST']  * 1.5)
        score += (player['STL']  * 2.5)
        score += (player['BLK']  * 2.5)
        score -= (player['TOV']  * 1.5)
        score += (player['PTS']  * 1.0)
        # games in progress
        score += (player.get('W_PCT', 0) * 2.0)
        score += (player.get('DD', 0) * 5.0)
        score += (player.get('TD', 0) * 15.0)
        score += (player.get('QD', 0) * 25.0)
        return round(score, 2)


class BBallReference(object):
    bball_ref_headers = [
        'PLAYER_NAME',
        'AGE',
        'POS',
        'GAME_DATE',
        'TEAM_ABBREVIATION',
        '',
        'OPP_TEAM_ABBREVIATION',
        'WINLOSS',
        '',
        'MIN',
        'FGM',
        'FGA',
        'FG%',
        '2P',
        '2PA',
        '2P%',
        '3PM',
        '3PA',
        '3P%',
        'FTM',
        'FTA',
        'FT%',
        'OREB',
        'DREB',
        'TRB',
        'AST',
        'STL',
        'BLK',
        'TOV',
        'PF',
        'PTS',
        'GMSC',
    ]

    boxscores_by_player = defaultdict(list)
    boxscores_by_date = defaultdict(list)

    def download_stats(self, season):
        logging.info("starting download of stats")
        time.sleep(5)
        from pathlib import Path
        for offset in range(0, 26100, 100):
            my_file = Path(f"{season}/{offset}.html")
            if my_file.is_file():
                logging.debug(f"already downloaded {season}/{offset}.html")
                continue
            time.sleep(30)

            url = f"https://www.basketball-reference.com/play-index/pgl_finder.cgi?request=1&player_id=&match=game&year_min={season}&year_max={season}&age_min=0&age_max=99&team_id=&opp_id=&season_start=1&season_end=-1&is_playoffs=N&draft_year=&round_id=&game_num_type=&game_num_min=&game_num_max=&game_month=&game_day=&game_location=&game_result=&is_starter=&is_active=&is_hof=&pos_is_g=Y&pos_is_gf=Y&pos_is_f=Y&pos_is_fg=Y&pos_is_fc=Y&pos_is_c=Y&pos_is_cf=Y&c1stat=&c1comp=&c1val=&c1val_orig=&c2stat=&c2comp=&c2val=&c2val_orig=&c3stat=&c3comp=&c3val=&c3val_orig=&c4stat=&c4comp=&c4val=&c4val_orig=&is_dbl_dbl=&is_trp_dbl=&order_by=pts&order_by_asc=&offset={offset}"
            response = requests.get(url)
            with open(f"{season}/{offset}.html", 'wb') as f:
                logging.debug(f"writing {season}/{offset}.html")
                f.write(response.content)

    def load_raw_stats(self, season):
        from bs4 import BeautifulSoup
        for statfile in os.listdir(f"{season}/"):
            with open(f"{season}/{statfile}") as f:
                try:
                    soup = BeautifulSoup(f.read(), 'html.parser')
                except UnicodeDecodeError:
                    logging.exception(f"Unicode Error in {statfile}", exc_info=True)
                    continue
                table = soup.find('table', {'id': 'stats'})
                rows = table.findAll('tr', {'class': ''})
                for row in rows:
                    cells = row.findAll('td')
                    values = [ele.text.strip() for ele in cells]
                    if len(values) != len(self.bball_ref_headers):
                        continue
                    player_game_data = {}
                    for header in self.bball_ref_headers:
                        player_game_data[header] = values.pop(0)
                    self.boxscores_by_player[player_game_data['PLAYER_NAME']].append(player_game_data)
                    self.boxscores_by_date[player_game_data['GAME_DATE']].append(player_game_data)

    def save_stats(self, season):
        with open(f"{season}-players.json", 'w') as f:
            json.dump(self.boxscores_by_player, f)
        with open(f"{season}-by-day.json", 'w') as f:
            json.dump(self.boxscores_by_date, f)

    def load_stats(self, season):
        with open(f"{season}-players.json", 'r') as f:
            self.boxscores_by_player = json.load(f)
        with open(f"{season}-by-day.json", 'r') as f:
            self.boxscores_by_date = json.load(f)


class NBA(object):
    def __init__(self, season):
        self.season = season

    def boxscore(self, game_id):
        url = f"https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/{self.season}/scores/gamedetail/{game_id}_gamedetail.json"
        response = requests.get(url)
        return response.json()


class ESPN(object):
    roster_by_player = {}

    def load_rosters(self):
        with open('espn_data.json') as f:
            raw_roster = json.load(f)
            logging.info(f"considering {len(raw_roster['players'])}")
            for player in raw_roster['players']:
                # logging.debug(f"player {player_name} is on {player.get('onTeamId')}")
                team_name = team_mapping.get(player.get('onTeamId', None), 'FA')
                self.roster_by_player[player.get('player').get('fullName')] = team_name


# b = BBallReference()
# b.download_stats('2018')
# b.load_raw_stats('2018')
# b.save_stats('2018')
# b.load_stats('2018')


from flask import Flask
app = Flask(__name__)
s = Schedule()
p = Players()
espn = ESPN()
espn.load_rosters()
nba = NBA('2018')

headers = [
    'player_name',
    'team',
    'espn_owner',
    'min',
    'fgm',
    'fga',
    'tpm',
    'tpa',
    'ftm',
    'fta',
    'oreb',
    'dreb',
    'ast',
    'stl',
    'blk',
    'tov',
    'pts',
    'fantasy_score',
]

@app.route('/leaders')
@app.route('/leaders/<game_day>')
def leaderboard(game_day=None):
    if not game_day:
        game_day = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d')
    games_today = s.schedule_by_date.get(game_day)

    response_html = f"<html><h3>{game_day}</h3><table border=2 width=1024>"
    response_html += "<tr>"
    for header in headers:
        response_html += f"<th>{header}</th>"
    response_html += "</tr>"

    todays_players = []
    for game in games_today:
        boxscore = nba.boxscore(game.get('gid'))
        try:
            for player in boxscore['g']['vls']['pstsg']:
                try:
                    player['fantasy_score'] = float('{:.2f}'.format(Players.calculate_fantasy_score(capitalize_keys(player))))
                    player['team'] = boxscore['g']['vls']['ta']
                    player['player_name'] = f"{player['fn']} {player['ln']}"
                    player['espn_owner'] = espn.roster_by_player.get(player['player_name'], 'FA')
                    todays_players.append(player)
                except Exception as e:
                    logging.exception(str(e), exc_info=True)
                    raise
                # print(f"{player['fn']} {player['ln']}\t{player['pts']}\t{fantasy_score}")
            for player in boxscore['g']['hls']['pstsg']:
                try:
                    player['fantasy_score'] = float('{:.2f}'.format(Players.calculate_fantasy_score(capitalize_keys(player))))
                    player['team'] = boxscore['g']['hls']['ta']
                    player['player_name'] = f"{player['fn']} {player['ln']}"
                    player['espn_owner'] = espn.roster_by_player.get(player['player_name'], 'FA')
                    todays_players.append(player)
                except Exception as e:
                    logging.exception(str(e), exc_info=True)
                    raise
        except KeyError:
            pass

    for player in sorted(todays_players, key=operator.itemgetter("fantasy_score"), reverse=True):
        response_html += "<tr align=right>"
        for header in headers:
            response_html += f"<td>{player[header]}</td>"
        # response_html += (f"{player['fn']} {player['ln']}\t{player['espn_owner']}\t{player['team_abbreviation']}\t{player['fantasy_score']}")
        response_html += "/<tr>"

    response_html += "</table>"
    return response_html


if __name__ == '__main__':
    app.run()

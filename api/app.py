from flask import Flask, render_template, jsonify
import requests
import yt_dlp
import random
import os
import time
import subprocess
from threading import Thread, Event
from datetime import datetime, timedelta

app = Flask(__name__, template_folder='../templates')

# Configurações globais
LASTFM_API_KEY = '9d7d79a952c5e5805a0decb0ccf1c9fd'

vinhetas = [
    "../static/vinhetas/vinheta_milenio.mp3",
    "../static/vinhetas/vinheta_rock.mp3",
    "../static/vinhetas/uma_hora.mp3"
]

cronograma = [
    {"estilo": "nu-metal", "duracao": 3},
    {"estilo": "alternative rock", "duracao": 3},
    {"estilo": "metalcore", "duracao": 3},
    {"estilo": "alt-rock", "duracao": 3},
    {"estilo": "indie rock", "duracao": 3},
    {"estilo": "brazilian rock", "duracao": 3},
]

# Variáveis de controle do estado da rádio
is_radio_running = False
musica_atual = None
musica_tocando = False
cronograma_index = 0
cronograma_event = Event()

@app.route('/')
def index():
    return render_template('index.html')

# Função para buscar músicas populares de um estilo na API do Last.fm
def buscar_musicas_por_estilo(estilo):
    url = f'http://ws.audioscrobbler.com/2.0/?method=tag.gettoptracks&tag={estilo}&api_key={LASTFM_API_KEY}&format=json'
    response = requests.get(url)
    data = response.json()
    if 'tracks' in data:
        return [(track['name'], track['artist']['name']) for track in data['tracks']['track']]
    return []

# Função para normalizar o áudio
def normalize_audio(input_file, output_file):
    command = [
        'ffmpeg', '-i', input_file, '-filter:a', 'volume=1.5', 
        '-acodec', 'libmp3lame', '-q:a', '0', output_file
    ]
    subprocess.run(command, check=True)

# Função para baixar e normalizar a música
def download_and_normalize_music(music_url, output_path):
    temp_path = output_path + ".temp.mp3"
    subprocess.run(['yt-dlp', music_url, '-o', temp_path], check=True)
    normalize_audio(temp_path, output_path)
    os.remove(temp_path)

# Função para baixar a música
def download_music(music_name, artist_name, result_container):
    sanitized_name = f"{artist_name} - {music_name}".replace("/", "_").replace("\\", "_").replace(":", "_").replace("!", "")
    output_path = f"static/musicas/{sanitized_name}.mp3"

    if os.path.exists(output_path):
        result_container["path"] = output_path
        return True

    ydl_opts = {
        'quiet': True, 'extract_audio': True, 'format': 'bestaudio/best', 
        'outtmpl': 'static/musicas/%(title)s.%(ext)s', 'noplaylist': True
    }

    search_query = f"{music_name} {artist_name} official music video"
    def attempt_download(query):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                search_results = ydl.extract_info(f"ytsearch:{query}", download=True)
                if 'entries' in search_results:
                    video = search_results['entries'][0]
                    temp_file = f"static/musicas/{video['title']}.webm"
                    output_file = f"static/musicas/{sanitized_name}.mp3"
                    subprocess.run(['ffmpeg', '-i', temp_file, '-q:a', '0', '-map', 'a', output_file])
                    os.remove(temp_file)
                    result_container["path"] = output_file
                    return True
            except Exception:
                result_container["path"] = None
        return False

    if not attempt_download(search_query):
        search_query = f"{music_name} {artist_name} official audio"
        return attempt_download(search_query)
    return True

# Função para tocar vinheta
def tocar_vinheta(vinheta):
    subprocess.run(['ffmpeg', '-i', vinheta, '-f', 'mp3', 'pipe:1'], stdout=subprocess.PIPE)

# Função para rodar o programa de rádio
def rodar_programa(estilo, duracao):
    global musica_atual, musica_tocando
    fim = datetime.now() + timedelta(minutes=duracao)

    while datetime.now() < fim:
        musicas = buscar_musicas_por_estilo(estilo)
        if musicas:
            musica, artista = random.choice(musicas)
            vinheta = random.choice(vinhetas)
            result_container = {"path": None}
            download_music(musica, artista, result_container)

            if result_container["path"]:
                musica_atual = musica
                musica_tocando = True
                tocar_vinheta(vinheta)
                subprocess.run(['ffmpeg', '-i', result_container["path"], '-f', 'mp3', 'pipe:1'], stdout=subprocess.PIPE)
            else:
                print(f"Erro ao baixar a música '{musica}'. Pulando...")
        else:
            print(f"Nenhuma música encontrada para o estilo: {estilo}")
        time.sleep(5)

# Função para rodar a rádio
def rodar_radio():
    global is_radio_running, cronograma_index, cronograma_event
    while is_radio_running:
        programa_atual = cronograma[cronograma_index]
        estilo = programa_atual["estilo"]
        duracao = programa_atual["duracao"]
        print(f"Iniciando programa: {estilo} por {duracao} minutos")
        rodar_programa(estilo, duracao)
        cronograma_event.wait(timeout=duracao * 60)
        cronograma_event.clear()
        cronograma_index = (cronograma_index + 1) % len(cronograma)

# Função para controle do cronograma
def controlador_cronograma():
    global cronograma_index, cronograma_event
    while True:
        # Pega o programa atual
        programa_atual = cronograma[cronograma_index]
        duracao = programa_atual["duracao"]
        
        print(f"Rodando programa: {programa_atual['estilo']} (duração: {duracao} minutos)")
        
        # Espera pela duração do programa ou até o evento ser acionado
        cronograma_event.wait(timeout=duracao * 60)
        
        # Reseta o evento e avança para o próximo programa
        cronograma_event.clear()
        cronograma_index = (cronograma_index + 1) % len(cronograma)

# Inicializa a thread de controle do cronograma
Thread(target=controlador_cronograma, daemon=True).start()

@app.route('/rodar_radio')
def rodar_radio_route():
    global is_radio_running
    if not is_radio_running:
        is_radio_running = True
        radio_thread = Thread(target=rodar_radio)
        radio_thread.start()
        return "Rádio iniciada!", 200
    else:
        return "Rádio já está tocando!", 200


# Função para avançar manualmente o cronograma
@app.route('/avancar_cronograma', methods=['POST'])
def avancar_cronograma():
    global cronograma_index, cronograma_event
    cronograma_index = (cronograma_index + 1) % len(cronograma)
    cronograma_event.set()
    return jsonify({"message": "Cronograma avançado com sucesso."}), 200

# Função para buscar a capa do álbum
def buscar_capa_do_album(musica, artista):
    url = f'http://ws.audioscrobbler.com/2.0/?method=track.getInfo&api_key={LASTFM_API_KEY}&artist={artista}&track={musica}&format=json'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if 'track' in data and 'album' in data['track']:
            album_info = data['track']['album']
            if 'image' in album_info and album_info['image']:
                return album_info['image'][-1]['#text']
    except Exception:
        pass

    google_search_url = f"https://www.google.com/search?tbm=isch&q={musica}+{artista}+album+cover"
    print(f"Buscando capa no Google Imagens: {google_search_url}")
    return "https://cdn.britannica.com/79/232779-050-6B0411D7/German-Shepherd-dog-Alsatian.jpg"

@app.route('/obter_proximo', methods=['GET'])
def obter_proximo():
    global cronograma, cronograma_index

    programa_atual = cronograma[cronograma_index]
    estilo = programa_atual["estilo"]
    musicas = buscar_musicas_por_estilo(estilo)

    if not musicas:
        return jsonify({"error": f"Nenhuma música encontrada para o estilo '{estilo}'."}), 404

    musica, artista = random.choice(musicas)
    vinheta = random.choice(vinhetas)

    result_container = {"path": None}
    download_music(musica, artista, result_container)

    music_path = result_container["path"]
    if not music_path:
        return jsonify({"error": f"Erro ao baixar a música '{musica}' de {artista}."}), 500

    capa_url = buscar_capa_do_album(musica, artista)

    return jsonify({
        "musica": {
            "nome": musica,
            "artista": artista,
            "url": f"/{music_path}",
            "estilo": estilo,
            "capa": capa_url
        },
        "vinheta": f"/{vinheta}"
    })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)


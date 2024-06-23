import os
import time
# import pygame
from tkinter import Tk  # Python 3


# get args from command line to select voice
# voice = sys.argv[1]
# example of usege python main.py en-US-SteffanNeural
# accepted arguments are: 
accepted_voices = [
    'ka-GE-EkaNeural',
    'en-US-SteffanNeural',
    'ru-RU-DariyaNeural',
    'en-GB-SoniaNeural',
]


voice = 'en-GB-SoniaNeural'

if len(os.sys.argv) > 1:
    lang = os.sys.argv[1]
    if lang == 'ka':
        voice = 'ka-GE-EkaNeural'
    elif lang == 'en':
        voice = 'en-GB-SoniaNeural'
    elif lang == 'ru':
        voice = 'ru-RU-SvetlanaNeural'
    elif lang == 'en-US':
        voice = 'en-US-SteffanNeural'
    else:
        print('Unknown language')
        print('Accepted languages are: ka, en, ru, en-US')
        exit(1)
 




def speak(data):
    # check if data has some text init
    if not data:
        return
    # replace special chars and new lines
    data = data.replace('"', "'")
    data = data.replace('\n', ' ')
    data = data.replace('\r', ' ')
    data = data.replace('\t', ' ')


    command = f'edge-tts --voice "{voice}" --text "{data}" --write-media "data.mp3"'
    # print(command)
    return_code = os.system(command)
    # Wait for command to finish


    print("Generating audio file in path {}\\data.mp3".format(os.path.abspath(os.getcwd())))

    if return_code != 0:
        print("Error")
        return
    else: 
        print("Audio file ready.")# Wait for 1 second before checking again

    # open audio file and play it
    os.system("data.mp3")


# read txt and put it in a speak function 
def read_txt(book_name="data.txt"):
    with open(book_name, 'r', encoding="utf-8") as f:
        print("Reading...")
        data = f.read()
        print(data[0:100])
        if data:
            speak(data)

def write_txt(data):
    with open("data.txt", 'w', encoding='utf-8') as f:
        f.write(data)


def tts(data = Tk().clipboard_get()):
    if data: 
        write_txt(data)
        read_txt()
    else:
        speak("Nothing to read")

if __name__ == "__main__":
    # read_txt()
    tts()
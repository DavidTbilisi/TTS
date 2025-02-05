import argparse
import os
from edge_tts import Communicate

def text_to_speech(text, language):
    """
    Converts the given text to speech in the specified language.
    
    Parameters:
    - text (str): The text to convert to speech.
    - language (str): The language code for the speech ('en' for English, 'ka' for Georgian, 'ru' for Russian).
    
    Returns:
    None
    """
    voice = {
        'ka': 'ka-GE-EkaNeural',
        'en': 'en-GB-SoniaNeural',
        'ru': 'ru-RU-SvetlanaNeural',
        'en-US': 'en-US-SteffanNeural'
    }.get(language, 'en-GB-SoniaNeural')

    command = f'edge-tts --voice "{voice}" --text "{text}" --write-media "data.mp3"'
    return_code = os.system(command)

    if return_code != 0:
        print("Error generating audio file.")
    else:
        print(f"Audio file generated at {os.path.abspath('data.mp3')}")
        os.system("data.mp3")

def main():
    parser = argparse.ArgumentParser(description='Text to Speech CLI')
    parser.add_argument('text', type=str, help='Text to convert to speech')
    parser.add_argument('--lang', type=str, default='en', help='Language of the text')
    args = parser.parse_args()

    text_to_speech(args.text, args.lang)

if __name__ == "__main__":
    main()
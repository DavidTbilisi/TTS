# Minimal pygame shim used only for tests.


class MixerMusic:
    @staticmethod
    def load(path):
        return None

    @staticmethod
    def play():
        return None


class Mixer:
    music = MixerMusic()

    @staticmethod
    def init():
        return None


def get_mixer():
    return Mixer()


# expose module-level mixer
mixer = Mixer()


def get_busy():
    return False


# provide module attributes used in tests
mixer.music = MixerMusic()

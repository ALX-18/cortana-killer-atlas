from kokoro_onnx import Kokoro
import soundfile as sf

kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")

print("Voix disponibles :")
for voice in kokoro.get_voices():
    print(f"  - {voice}")

samples, sample_rate = kokoro.create(
    "Hey ma star, comment tu vas aujourd'hui ? C'est moi, Rori.",
    voice="ff_siwis",
    speed=1.0,
    lang="fr-fr"
)
sf.write("test_kokoro_rori.wav", samples, sample_rate)
print("Fichier généré : test_kokoro_rori.wav")

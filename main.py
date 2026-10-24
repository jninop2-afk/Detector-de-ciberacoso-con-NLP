"""Punto de entrada del proyecto.

    python main.py                 consola interactiva de pruebas
    python main.py train           entrena el modelo clásico
    python main.py train-roberta   fine-tuning de RoBERTuito (5 categorías)
    python main.py audit           detecta etiquetas sospechosas en el dataset
    python main.py bot             inicia el bot de Discord
"""

import argparse
import sys


def run_interactive_cli(use_roberta: bool):
  from src.predict import CyberbullyingDetector

  print('=' * 65)
  print('   DETECTOR DE CIBERACOSO (NLP + ML + RoBERTa) - CONSOLA')
  print('=' * 65)
  print('Cargando modelos...')
  try:
    detector = CyberbullyingDetector(use_roberta=use_roberta)
    detector.warmup()
  except Exception as e:
    print(f' Error al cargar el detector: {e}')
    sys.exit(1)
  print(f' Modelos cargados. RoBERTa: {detector.roberta_mode}')
  print("\nEscribe un texto para analizarlo ('salir' para terminar).")

  while True:
    try:
      user_input = input('\n Mensaje > ').strip()
    except (KeyboardInterrupt, EOFError):
      print('\nSaliendo...')
      break
    if not user_input:
      continue
    if user_input.lower() in ('salir', 'exit', 'quit'):
      break

    r = detector.predict(user_input)
    print('─' * 60)
    print(f' Preprocesado      : "{r["texto_limpio"]}"')
    if r['es_ciberacoso']:
      print(' DIAGNÓSTICO       : [ POSIBLE CIBERACOSO ]')
      print(f' CATEGORÍA         : {r["categoria"]} - {r["categoria_nombre"]}')
    else:
      print(' DIAGNÓSTICO       : [ MENSAJE SEGURO ]')
    print(f' CONFIANZA         : {r["confianza"] * 100:.2f}%')
    print(f' MOTOR             : {r["motor"]}')
    print(f' P(acoso) clásico  : {r["prob_clasico"]}   RoBERTa: {r["prob_roberta"]}')
    print(' DISTRIBUCIÓN 0-4  : ' + '  '.join(
        f'{c}:{p:.2f}' for c, p in r['probabilidades'].items()))
    if r['motivos_sospecha']:
      print(' SOSPECHAS         : ' + '; '.join(r['motivos_sospecha']))
    print(f' ACCIÓN SUGERIDA   : {r["accion_sugerida"]}')
    print('─' * 60)


def main():
  parser = argparse.ArgumentParser(description='Detector de ciberacoso')
  sub = parser.add_subparsers(dest='cmd')
  cli = sub.add_parser('cli', help='Consola interactiva (por defecto)')
  cli.add_argument('--sin-roberta', action='store_true')
  sub.add_parser('train', help='Entrena el modelo clásico')
  sub.add_parser('train-roberta', help='Fine-tuning de RoBERTuito', add_help=False)
  sub.add_parser('audit', help='Audita etiquetas del dataset')
  sub.add_parser('bot', help='Inicia el bot de Discord')
  args, extra = parser.parse_known_args()

  if args.cmd == 'train':
    from src.train import train_classic
    train_classic()
  elif args.cmd == 'train-roberta':
    from src.train_transformer import main as train_roberta
    train_roberta(extra)
  elif args.cmd == 'audit':
    from src.label_audit import audit_labels
    audit_labels()
  elif args.cmd == 'bot':
    from src.bot_Discord.bot import main as run_bot
    run_bot()
  else:
    run_interactive_cli(use_roberta=not getattr(args, 'sin_roberta', False))


if __name__ == '__main__':
  main()

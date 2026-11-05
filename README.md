# YAS File Tool
[![Tests](https://github.com/ShmaltsIO/YAS_FileTool/actions/workflows/tests.yml/badge.svg)](https://github.com/ShmaltsIO/YAS_FileTool/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/ShmaltsIO/YAS_FileTool)](https://github.com/ShmaltsIO/YAS_FileTool/releases)
[![License](https://img.shields.io/github/license/ShmaltsIO/YAS_FileTool)](LICENSE)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey)

![icon](src/yas_filetool/assets/images/icon_512.png)

GUI-утилита для наведения порядка в фото- и медиа- архиве: поиск и вынос
дубликатов, массовое переименование, конвертация изображений, видео и аудио.
Одинаково работает на Windows и Linux (Python 3.12 + PyQt6).

> ⚠ **Утилита ничего не удаляет** без явного разрешения. Все операции
> пишут CSV-отчёт, который можно использовать для отката. CSV открывается в MS Excel/LibreOffice Calc.

---

## Возможности

| Вкладка | Что делает |
|---|---|
| **Поиск дубликатов** | Ищет одинаковые фотографии через каскад проверок: pHash-256 + dHash-256 + PSNR + P99 abs-diff + SSIM (+ gradient SSIM опционально). Понимает разные форматы, разрешения и имена. Режимы «одна папка» и «две папки» (с защищёнными). Аудит и откат по отчёту. |
| **Переименовать файлы** | Шаблон `префикс_постфикс_N.ext`. Рекурсия, имена подпапок, опция «убрать корень», авто-нумерация с паддингом по количеству файлов в каждой папке. Атомарная замена через temp-имена. |
| **Конвертер** | Фото: `.jpg/.png/.webp/.bmp/.tiff`. Видео: `.mp4/.mkv/.webm/.mov/.avi` (ffmpeg). Аудио: `.mp3/.wav/.flac/.ogg/.opus/.m4a`. GIF: анимация → MP4/WEBM, либо первый кадр → PNG/JPG/WEBP. Извлечение звука из видео. Прогресс текущего файла в реальном времени. |
| **Настройки** | Пороги верификации, качество JPEG/WEBP, CRF и preset для видео, битрейт аудио. Сохраняется в `config/settings.toml`. |

---

## Установка

### Требования

- **Python 3.12**
- **[Poetry](https://python-poetry.org/docs/#installation)**
- **Windows 10/11** или **Linux** (X11/Wayland)
- **ffmpeg** — необязательно: для видео и аудио подтягивается
  автоматически через `imageio-ffmpeg` (статический бинарник). Если в
  системе уже есть свежий ffmpeg — он будет использоваться вместо
  встроенного.

### Шаги

```bash
# 1. Клонировать репозиторий
git clone https://github.com/ShmaltsIO/YAS_FileTool.git yas_filetool
cd yas_filetool

# 2. Явно указать Python 3.12 (если в системе несколько версий)
poetry env use python3.12
# Windows:
#   poetry env use py -3.12

# 3. Установить зависимости
poetry install

# 4. Запустить
poetry run yas-filetool
```

## Лицензия

**MIT.** Используйте, модифицируйте, распространяйте свободно, в том числе
коммерчески. Программа предоставляется «как есть», без гарантий. Автор
не несёт ответственности за потерю данных.
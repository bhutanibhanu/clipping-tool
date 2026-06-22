"""Job orchestration: ingest -> transcribe -> detect -> render. Built across Phases 1-4.

Runs as a single in-process worker (concurrency = 1) so Whisper and ffmpeg
never contend for the 8 GB M1 Air's RAM.
"""

@echo off
rem Run Mininet in Docker from Command Prompt or by double-clicking.
rem Usage: scripts\mininet-docker.cmd [-Build] [command ...]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mininet-docker.ps1" %*

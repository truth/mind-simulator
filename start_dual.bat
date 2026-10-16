@echo off
rem 双机模式：两架模拟飞机，可由两部手机分别控制
rem   飞机 #1：手机 App 填 电脑IP:8889（Mind+ 仍连 192.168.10.1）
rem   飞机 #2：手机 App 填 电脑IP:8989
call "%~dp0start.bat" --drones 2 %*

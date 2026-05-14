@REM @echo off
@REM setlocal enabledelayedexpansion

@REM set "target_dir=Y:\"
@REM set "output=report.csv"

@REM echo Folder,FileCount,Size> %output%

@REM for /d %%G in ("%target_dir%*") do (

@REM     set "folder_name=%%~nxG"
@REM     set "f_count=0"
@REM     set "f_size=0"

@REM     for /f "tokens=1-3" %%A in ('robocopy "%%G" NUL /L /S /NFL /NDL /R:0 /W:0 /NJH ^| findstr /R /C:"Files :" /C:"Bytes :"') do (
@REM         if "%%A"=="Files" set "f_count=%%C"
@REM         if "%%A"=="Bytes" set "f_size=%%C"
@REM     )

@REM     echo !folder_name!,!f_count!,!f_size! >> %output%
@REM )

@REM echo Done! File saved: %output%
@REM pause

@echo off
setlocal enabledelayedexpansion

set "target_dir=Y:\"
set "output=report.csv"

echo Folder,FileCount,SizeBytes > %output%

for /d %%G in ("%target_dir%*") do (

    set "folder_name=%%~nxG"
    set "f_count=0"
    set "f_size=0"

    for /f "tokens=1-3" %%A in ('robocopy "%%G" NUL /L /S /NFL /NDL /NJH /BYTES /R:0 /W:0 ^| findstr /R /C:"Files :" /C:"Bytes :"') do (

        if "%%A"=="Files" set "f_count=%%C"
        if "%%A"=="Bytes" set "f_size=%%C"
    )

    echo !folder_name!,!f_count!,!f_size! >> %output%
)

echo Done! File saved: %output%
pause
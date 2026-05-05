[app]
title        = MAC to M3U PRO
package.name = mac2m3u
package.domain = com.iptv.tools
version      = 1.0.0
source.dir   = .
source.include_exts = py,png,jpg,kv,atlas,json
requirements = python3==3.11.6,kivy==2.3.0,aiohttp==3.9.5,aiosignal,frozenlist,multidict,yarl,attrs,charset-normalizer
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api  = 33
android.minapi = 26
android.ndk  = 25b
android.archs = arm64-v8a,armeabi-v7a
android.orientation = portrait
android.enable_androidx = True
[buildozer]
log_level = 2
warn_on_root = 0

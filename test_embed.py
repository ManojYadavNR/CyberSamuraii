import requests, re
r = requests.get('https://www.instagram.com/p/DBk058vB0Q4/embed/')
urls = re.findall(r'https?://[^"'\'']+\.mp4[^"'\'']*', r.text)
print('Found URLs:', len(urls))
if urls: print(urls[0].replace('\\u0026', '&'))

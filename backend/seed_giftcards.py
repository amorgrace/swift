import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "engine.settings")
django.setup()

from rates.models import GiftCard

GIFT_CARDS = [
  { "brand":"Amazon",      "category":"Amazon",      "color":"#FF9900", "bg":"linear-gradient(135deg,#1a0800,#3d1f00)", "denominations":["$25","$50","$100","$200"], "rates":{"$25":34500,"$50":68000,"$100":137000,"$200":270000}, "rate_per_dollar":1380, "country":"USA", "popular":True },
  { "brand":"Amazon",      "category":"Amazon",      "color":"#FF9900", "bg":"linear-gradient(135deg,#0d1a00,#1a3300)", "denominations":["£25","£50","£100"], "rates":{"£25":41000,"£50":81000,"£100":160000}, "rate_per_dollar":1640, "country":"UK", "popular":False },
  { "brand":"Steam",       "category":"Steam",       "color":"#66C0F4", "bg":"linear-gradient(135deg,#00101a,#001f33)", "denominations":["$10","$20","$50","$100"], "rates":{"$10":13000,"$20":25500,"$50":63000,"$100":125000}, "rate_per_dollar":1300, "country":"USA", "popular":True },
  { "brand":"iTunes",      "category":"iTunes",      "color":"#FC3C44", "bg":"linear-gradient(135deg,#1a0010,#330020)", "denominations":["$15","$25","$50","$100"], "rates":{"$15":20000,"$25":33750,"$50":67000,"$100":135000}, "rate_per_dollar":1350, "country":"USA", "popular":True },
  { "brand":"iTunes",      "category":"iTunes",      "color":"#FC3C44", "bg":"linear-gradient(135deg,#100010,#200020)", "denominations":["£15","£25","£50"], "rates":{"£15":24000,"£25":39000,"£50":78000}, "rate_per_dollar":1560, "country":"UK", "popular":False },
  { "brand":"Google Play", "category":"Google Play", "color":"#0ECB81", "bg":"linear-gradient(135deg,#001a08,#003318)", "denominations":["$10","$25","$50","$100"], "rates":{"$10":13700,"$25":34250,"$50":68500,"$100":137000}, "rate_per_dollar":1370, "country":"USA", "popular":False },
  { "brand":"Netflix",     "category":"Netflix",     "color":"#E50914", "bg":"linear-gradient(135deg,#1a0000,#330000)", "denominations":["$15","$30","$60","$100"], "rates":{"$15":19500,"$30":39000,"$60":78000,"$100":130000}, "rate_per_dollar":1300, "country":"USA", "popular":True },
  { "brand":"Visa",        "category":"Visa",        "color":"#1A1F71", "bg":"linear-gradient(135deg,#000818,#00102d)", "denominations":["$50","$100","$200","$500"], "rates":{"$50":63000,"$100":125000,"$200":248000,"$500":615000}, "rate_per_dollar":1260, "country":"USA", "popular":False },
  { "brand":"Xbox",        "category":"Xbox",        "color":"#107C10", "bg":"linear-gradient(135deg,#001a00,#003300)", "denominations":["$10","$25","$50","$100"], "rates":{"$10":12800,"$25":31500,"$50":62500,"$100":124000}, "rate_per_dollar":1280, "country":"USA", "popular":False },
]

def seed():
    GiftCard.objects.all().delete()
    for item in GIFT_CARDS:
        GiftCard.objects.create(**item)
    print("Database seeded with Gift Cards!")

if __name__ == "__main__":
    seed()

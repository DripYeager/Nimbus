"""
Facts behind the large retrieval benchmark: families of look-alike documents (many invoices, many
meetings, many trips...) so search must tell similar files apart. Each entry also carries a
paraphrase of its key fact, worded so it shares as few words as possible with the document.
Data only; scripts/build_eval_corpus.py turns it into files and labelled questions.
"""

from __future__ import annotations

# (vendor, item, quantity, unit price, what someone would call the item without its name)
INVOICES = [
    ("Contoso Furniture", "standing desks", 12, 540, "height-adjustable tables"),
    ("Fabrikam Print", "business cards", 2000, 0.08, "little cards with our contact details"),
    ("Tailspin Coffee", "espresso machine servicing", 1, 380, "repair of the coffee maker"),
    ("Litware Labs", "penetration test", 1, 9200, "hiring outside hackers to probe our systems"),
    ("Northwind Cleaning", "monthly office cleaning", 1, 1150, "the people who tidy the workplace"),
    ("Adatum Security", "door access badges", 60, 14, "key cards for getting into the building"),
    ("Proseware Cloud", "object storage", 1, 640, "space for keeping files on remote servers"),
    ("Woodgrove Catering", "team lunch catering", 1, 870, "food brought in for the staff meal"),
    ("Lucerne Legal", "trademark filing", 1, 2400, "registering our brand name officially"),
    ("Wingtip Toys", "promotional plush toys", 300, 6, "soft giveaway animals for a trade fair"),
    ("Coho Vineyard", "client gift wine", 24, 31, "bottles sent to customers as thank-you presents"),
    ("Margie Travel", "conference flights", 6, 420, "plane tickets for the summit trip"),
    ("Humongous Insurance", "cyber liability cover", 1, 3100, "protection if we get hacked"),
    ("Blue Yonder Airlines", "excess baggage fees", 3, 75, "extra charges for heavy suitcases"),
    ("Alpine Ski House", "team offsite lodge", 1, 4800, "mountain cabin rental for the away days"),
    ("Trey Research", "customer survey panel", 1, 5600, "paying people to answer our questionnaire"),
    ("Graphic Design Institute", "logo redesign", 1, 3900, "a new look for our brand symbol"),
    ("School of Fine Art", "team painting workshop", 14, 45, "an art class for colleagues"),
    ("City Power and Light", "office electricity", 1, 1320, "the energy bill for the workplace"),
    ("VanArsdel Plants", "office plant rental", 30, 9, "renting greenery for the desks"),
]
# (codename, goal, goal paraphrase, owner, deadline)
PROJECTS = [
    (
        "Atlas",
        "move the HR system to the cloud",
        "shifting staff records off our own servers",
        "Dana Whitfield",
        "March",
    ),
    ("Borealis", "launch the mobile app in Canada", "releasing the phone app to Canadian users", "Luis Ortega", "June"),
    ("Cascade", "replace the warehouse barcode scanners", "new handheld readers in the depot", "Mei Lin", "April"),
    ("Delta", "cut cloud spending by twenty percent", "trimming the hosting bill by a fifth", "Omar Haddad", "May"),
    ("Ember", "build a customer loyalty points scheme", "rewarding repeat shoppers", "Grace Kim", "September"),
    ("Fjord", "open a sales office in Oslo", "a new branch in the Norwegian capital", "Erik Nilsen", "October"),
    ("Granite", "rewrite the invoicing engine in Go", "rebuilding billing in a new language", "Priya Shah", "November"),
    ("Harbor", "consolidate the three support inboxes", "merging the help desk mailboxes", "Tom Reyes", "February"),
    ("Iris", "add single sign-on for enterprise clients", "one login across company tools", "Ana Costa", "July"),
    ("Juniper", "redesign the onboarding emails", "the welcome messages new users receive", "Sam Patel", "August"),
    (
        "Kestrel",
        "pilot drone deliveries in rural areas",
        "flying parcels to the countryside",
        "Nadia Bello",
        "December",
    ),
    (
        "Lumen",
        "switch the offices to LED lighting",
        "more efficient bulbs throughout the buildings",
        "Chris Moore",
        "January",
    ),
    ("Monsoon", "build a disaster recovery site", "a backup location if the main one fails", "Ravi Iyer", "June"),
    ("Nimbus Labs", "evaluate local AI assistants", "testing on-device chat helpers", "Ella Brooks", "March"),
    ("Orchard", "launch a farm-to-table meal kit", "boxes of fresh ingredients delivered weekly", "Jonah Weiss", "May"),
]
# (city, country, sights, food, food paraphrase)
TRIPS = [
    ("Kyoto", "Japan", "Fushimi Inari shrine and the bamboo grove", "matcha ice cream", "green tea frozen dessert"),
    ("Reykjavik", "Iceland", "the Blue Lagoon and the Golden Circle", "fermented shark", "the rotten fish delicacy"),
    (
        "Marrakesh",
        "Morocco",
        "Jemaa el-Fnaa square and the Majorelle garden",
        "lamb tagine",
        "slow-cooked meat in a clay pot",
    ),
    ("Naples", "Italy", "Pompeii and Mount Vesuvius", "margherita pizza", "the classic tomato and mozzarella pie"),
    ("Hanoi", "Vietnam", "Ha Long Bay and the Old Quarter", "pho", "the noodle soup with herbs"),
    ("Edinburgh", "Scotland", "the castle and Arthur's Seat", "haggis", "the sheep offal dish"),
    ("Oaxaca", "Mexico", "Monte Alban and the Sunday market", "mole negro", "the dark chocolate chilli sauce"),
    ("Tbilisi", "Georgia", "the sulfur baths and Narikala fortress", "khachapuri", "cheese-filled bread boat"),
    (
        "Cape Town",
        "South Africa",
        "Table Mountain and Boulders Beach",
        "bobotie",
        "spiced mince baked with egg custard",
    ),
    ("Istanbul", "Turkey", "the Hagia Sophia and the Grand Bazaar", "baklava", "the honey and nut pastry"),
    ("Lima", "Peru", "the Larco Museum and Miraflores cliffs", "ceviche", "raw fish cured in lime"),
    ("Seoul", "South Korea", "Gyeongbokgung palace and Bukchon village", "bibimbap", "the mixed rice bowl"),
]
# (dish, key ingredient, oven or method, paraphrase of the dish)
RECIPES = [
    ("banana bread", "three overripe bananas", "bake at 175 C for 60 minutes", "the loaf made from brown fruit"),
    ("shakshuka", "six eggs", "simmer covered for 8 minutes", "eggs poached in spiced tomato sauce"),
    ("chicken tikka masala", "500 g chicken thighs", "grill the marinated pieces first", "the creamy orange curry"),
    ("ratatouille", "two aubergines", "roast at 200 C for 45 minutes", "the baked summer vegetable stew"),
    ("pad thai", "200 g rice noodles", "stir-fry on high heat", "the sweet and sour noodle dish"),
    (
        "lemon drizzle cake",
        "two unwaxed lemons",
        "bake at 180 C for 45 minutes",
        "the citrus sponge with a sugary glaze",
    ),
    ("mushroom risotto", "300 g arborio rice", "add stock a ladle at a time", "the creamy Italian rice with fungi"),
    ("beef chili", "two tins of kidney beans", "simmer for two hours", "the spicy meat and bean stew"),
    ("falafel", "dried chickpeas soaked overnight", "deep fry at 180 C", "the fried chickpea balls"),
    (
        "apple crumble",
        "four Bramley apples",
        "bake at 190 C for 35 minutes",
        "the fruit pudding with a buttery topping",
    ),
    ("miso soup", "two tablespoons of white miso", "never let it boil", "the Japanese fermented bean broth"),
    ("focaccia", "olive oil and flaky salt", "proof for two hours then bake at 220 C", "the dimpled flat bread"),
]
# (agreement, provider, notice period, fee or cover, paraphrase of what it is)
AGREEMENTS = [
    ("gym membership", "PowerHouse Fitness", "one month", "39 GBP per month", "the workout club"),
    ("mobile phone contract", "Skyline Mobile", "30 days", "24 GBP per month", "my cell plan"),
    ("home contents insurance", "Shield Mutual", "14 days", "180 GBP per year", "cover for my belongings at home"),
    ("broadband contract", "FibreNet", "60 days", "35 GBP per month", "the home internet deal"),
    ("pet insurance", "PawSure", "14 days", "22 GBP per month for the dog", "cover for vet bills"),
    ("car lease", "DriveEasy", "three months", "310 GBP per month", "renting the vehicle long term"),
    ("streaming subscription", "CineStream", "any time", "11 GBP per month", "the film and TV service"),
    ("cleaning service", "Sparkle Home", "two weeks", "60 GBP per visit", "the person who cleans the house"),
    ("parking permit", "City Council", "one month", "45 GBP per quarter", "the right to leave my car on the street"),
    ("software licence", "DesignPro", "90 days before renewal", "480 USD per year", "the illustration program"),
    ("storage unit rental", "BoxIt Storage", "28 days", "95 GBP per month", "the locker where old furniture sits"),
    ("music lessons", "Harmony Academy", "half a term", "28 GBP per lesson", "the piano classes"),
]
# (who, specialty, place, when, paraphrase)
APPOINTMENTS = [
    ("Dr. Patel", "optician", "ClearView Eyecare", "Monday 3 November at 11:00", "my eye test"),
    ("Dr. Moreau", "dermatologist", "SkinWell Clinic", "Thursday 6 November at 15:30", "the mole check"),
    ("Sarah Lee", "physiotherapist", "MoveBetter Physio", "Friday 7 November at 08:15", "treatment for my bad knee"),
    ("Dr. Anand", "cardiologist", "Heartline Hospital", "Wednesday 12 November at 10:00", "the heart specialist visit"),
    ("Mike Grant", "barber", "Sharp Cuts", "Saturday 8 November at 09:45", "my next haircut"),
    ("Dr. Novak", "vet", "Paws and Claws", "Tuesday 18 November at 17:00", "the dog's vaccinations"),
    ("Linda Park", "accountant", "Park and Co", "Monday 24 November at 14:00", "going over my tax paperwork"),
    ("Dr. Haines", "orthodontist", "Bright Smiles", "Thursday 20 November at 16:15", "my daughter's braces check"),
    ("Ben Ortiz", "mechanic", "Ortiz Motors", "Friday 14 November at 08:00", "the car service"),
    ("Dr. Wu", "allergist", "Allergy Partners", "Wednesday 26 November at 13:30", "the hay fever tests"),
]
# (title, body, direct question, paraphrased question)
GUIDES = [
    (
        "Printer setup",
        "Add the office printer PRN-4F via Settings, Printers. Use the code 4417 at the release station.",
        "PRN-4F printer",
        "how do I get my pages to come out of the machine on the fourth floor",
    ),
    (
        "Expense policy",
        "Meals while travelling are reimbursed up to 45 GBP a day. Submit receipts within 30 days in Spendly.",
        "expense policy receipts Spendly",
        "how much can I spend on food when I'm away for work",
    ),
    (
        "Parental leave",
        "Primary carers get 26 weeks at full pay; secondary carers get 6 weeks. Tell HR 15 weeks before the due date.",
        "parental leave weeks full pay",
        "how long can I stay home after the baby arrives",
    ),
    (
        "Password rules",
        "Passwords need 14 characters and change every 180 days. Never reuse your last 10 passwords.",
        "password 14 characters",
        "how long must my login secret be",
    ),
    (
        "Fire drill",
        "Leave by the nearest stairwell and meet at assembly point B in the north car park.",
        "fire drill assembly point",
        "where do we gather when the alarm goes off",
    ),
    (
        "Holiday allowance",
        "Staff get 25 days of annual leave plus bank holidays. Up to 5 days can carry over to next year.",
        "annual leave 25 days",
        "how many days off do I get a year",
    ),
    (
        "Laptop return",
        "Leavers return laptops to IT on their last day. Wipe nothing; IT keeps a backup for 90 days.",
        "laptop return leavers",
        "what happens to my computer when I quit",
    ),
    (
        "Garden watering",
        "Water the tomatoes every morning and the lawn twice a week. The hose timer is set for 6 am.",
        "water tomatoes lawn hose timer",
        "when does the sprinkler come on",
    ),
    (
        "Bike maintenance",
        "Pump the tyres to 80 psi, oil the chain monthly and replace brake pads every 2,000 km.",
        "bike tyres 80 psi chain",
        "how often should the stopping pads on my bicycle be changed",
    ),
    (
        "Recycling rules",
        "Blue bin for paper and card, green for glass, grey for general waste. Collection is every Tuesday.",
        "blue bin paper green glass",
        "which container do empty jam jars go in",
    ),
    (
        "Boiler reset",
        "If the boiler shows fault E119, top up the pressure to 1.5 bar using the filling loop, then press reset.",
        "boiler fault E119",
        "the heating stopped and shows an error code, what do I do",
    ),
    (
        "Wedding plan",
        "Ceremony at 2 pm at St Mary's, reception at The Old Barn, 120 guests, band starts at 8 pm.",
        "wedding reception Old Barn",
        "where is the party after the vows",
    ),
    (
        "Moving checklist",
        "Book the van for the 15th, redirect post, read the meters on the day and give the landlord the keys.",
        "moving van redirect post",
        "things to sort out before I change house",
    ),
    (
        "Book club",
        "This month we read The Remains of the Day. Meeting at Ana's flat on the 21st at 7 pm.",
        "book club Remains of the Day",
        "which novel are we discussing this month",
    ),
    (
        "Running shoes",
        "Replace running shoes every 700 km. Current pair bought in March, logged 540 km so far.",
        "running shoes 700 km",
        "when do I need new trainers for jogging",
    ),
    (
        "Home network",
        "The NAS lives at 192.168.1.20. Backups run nightly at 2 am to the external drive.",
        "NAS 192.168.1.20 backups",
        "when does my computer copy its files to the spare disk",
    ),
    (
        "Vaccination record",
        "Tetanus booster given in 2021, next due 2031. Flu jab every October at the pharmacy.",
        "tetanus booster 2031",
        "when is my next jab for rusty-nail infections due",
    ),
    (
        "Board game night",
        "Bring snacks; we play Catan first, then Codenames. Starts at 7 at Leo's.",
        "board game Catan Codenames",
        "what are we playing at the games evening",
    ),
    (
        "Car tyres",
        "Winter tyres are stored at Ortiz Motors. Swap them in late October; tread must be at least 3 mm.",
        "winter tyres stored Ortiz",
        "where are the cold-weather wheels kept",
    ),
]

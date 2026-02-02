import asyncio
import os
import shutil
import time
import hashlib
import random
import httpx
from PIL import Image
from io import BytesIO
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends
from faker import Faker
from tqdm.asyncio import tqdm
from dotenv import load_dotenv
from app.database.database import get_db
from app.database.seeders.categories import seed_categories
from app.database.seeders.suppliers import seed_suppliers
from app.database.seeders.orders import seed_orders
from app.database.tables import (
    Category,
    Supplier,
    Product,
    Order,
    User,
)
from app.database.database import SessionLocal
from app.database.database import engine, Base, root_engine
from app.schemas.schemas import UserCreate
from app.controllers.auth_controller import register_new_user

load_dotenv()

fake = Faker()

# Pexels API key - get free key at https://www.pexels.com/api/
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# List of common English nouns for product names
NOUNS = [
    "Chair",
    "Table",
    "Lamp",
    "Phone",
    "Watch",
    "Camera",
    "Laptop",
    "Keyboard",
    "Mouse",
    "Monitor",
    "Speaker",
    "Headphones",
    "Tablet",
    "Printer",
    "Scanner",
    "Desk",
    "Sofa",
    "Bed",
    "Mirror",
    "Clock",
    "Vase",
    "Plant",
    "Book",
    "Pen",
    "Notebook",
    "Bag",
    "Wallet",
    "Belt",
    "Hat",
    "Scarf",
    "Gloves",
    "Jacket",
    "Shirt",
    "Pants",
    "Shoes",
    "Boots",
    "Sneakers",
    "Sandals",
    "Socks",
    "Tie",
    "Dress",
    "Skirt",
    "Sweater",
    "Coat",
    "Umbrella",
    "Sunglasses",
    "Ring",
    "Necklace",
    "Bracelet",
    "Earrings",
    "Perfume",
    "Candle",
    "Towel",
    "Pillow",
    "Blanket",
    "Curtain",
    "Carpet",
    "Frame",
    "Poster",
    "Calendar",
    "Globe",
    "Telescope",
    "Binoculars",
    "Compass",
    "Backpack",
    "Suitcase",
    "Bottle",
    "Mug",
    "Plate",
    "Bowl",
    "Fork",
    "Knife",
    "Spoon",
    "Pan",
    "Pot",
    "Kettle",
    "Toaster",
    "Blender",
    "Mixer",
    "Oven",
    "Microwave",
    "Refrigerator",
    "Fan",
    "Heater",
    "Vacuum",
    "Iron",
    "Dryer",
    "Washer",
    "Television",
    "Radio",
    "Guitar",
    "Piano",
    "Violin",
    "Drums",
    "Flute",
    "Trumpet",
    "Bicycle",
    "Skateboard",
    "Scooter",
    "Helmet",
    "Ball",
    "Racket",
    "Glove",
    "Bat",
]


def hash_filename(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


async def search_pexels_image(query: str) -> str | None:
    """Search for image URL using Pexels API."""
    if not PEXELS_API_KEY:
        print("Warning: PEXELS_API_KEY not set!")
        return None

    url = f"https://api.pexels.com/v1/search?query={query}&per_page=10"
    headers = {"Authorization": PEXELS_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                photos = data.get("photos", [])
                if photos:
                    # Pick random photo from results
                    photo = random.choice(photos)
                    # Get large size image URL
                    return photo.get("src", {}).get("large")
            else:
                print(f"Pexels API error: {response.status_code}")
    except Exception as e:
        print(f"Pexels search failed for '{query}': {e}")

    return None


async def download_image_from_url(url: str, file_name: str, base_folder: str) -> bool:
    """Download image from URL and save in multiple sizes."""
    sizes = [(500, 500), (100, 100), (1000, 1000), (10, 10)]

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content))
                # Convert to RGB if necessary
                if img.mode in ("RGBA", "P", "LA", "L"):
                    img = img.convert("RGB")

                for size in sizes:
                    size_folder = os.path.join(base_folder, f"{size[0]}x{size[1]}")
                    os.makedirs(size_folder, exist_ok=True)

                    resized_img = img.resize(size, Image.Resampling.LANCZOS)
                    resized_img.save(
                        os.path.join(size_folder, f"{file_name}.png"), format="PNG"
                    )
                return True
    except Exception as e:
        print(f"Download failed: {e}")
    return False


async def download_fallback_image(file_name: str, base_folder: str) -> bool:
    """Download fallback image from Lorem Picsum."""
    seed = random.randint(1, 1000)
    url = f"https://picsum.photos/seed/{seed}/1000/1000"
    return await download_image_from_url(url, file_name, base_folder)


async def seed_products_from_internet(db: Session, num_products: int):
    """Seed products with real images searched from Pexels by product name."""
    categories = db.query(Category).all()
    suppliers = db.query(Supplier).all()

    category_ids = [c.id for c in categories]
    supplier_ids = [s.id for s in suppliers]
    products_to_add = []

    name_count = {}

    async for i in tqdm(range(num_products), desc="Seeding Products"):
        # Use single noun from the list
        base_name = NOUNS[i % len(NOUNS)]

        # Handle duplicate names
        if base_name in name_count:
            name_count[base_name] += 1
            product_name = f"{base_name} {name_count[base_name]}"
        else:
            name_count[base_name] = 1
            product_name = base_name

        hashed_name = hash_filename(product_name)
        photo_folder = "static/images/"
        os.makedirs(photo_folder, exist_ok=True)

        # Search and download image from Pexels by product name
        print(f"Searching image for: {product_name}")
        image_url = await search_pexels_image(base_name)

        success = False
        if image_url:
            print(f"Found: {image_url[:60]}...")
            success = await download_image_from_url(
                image_url, hashed_name, photo_folder
            )

        if not success:
            print(f"Using fallback for: {product_name}")
            await download_fallback_image(hashed_name, photo_folder)

        # Random description that doesn't match the product
        random_description = fake.text(max_nb_chars=200)

        product = Product(
            name=product_name,
            description=random_description,
            price=fake.random_number(digits=3),
            category_id=fake.random_element(elements=category_ids),
            supplier_id=fake.random_element(elements=supplier_ids),
            quantity=fake.random_number(digits=2),
            photo_path=f"{hashed_name}.png",
        )
        products_to_add.append(product)

    # Bulk save all products
    db.bulk_save_objects(products_to_add)
    db.commit()
    print(f"Added {len(products_to_add)} products with images")


def create_tables():
    print("Creating tables...")
    Base.metadata.create_all(bind=root_engine)
    print("Tables created successfully.")


def create_main_user():
    user = UserCreate(username="root", email="root@root.root", password="root")
    db = SessionLocal()

    existing_user = db.query(User).filter(User.username == user.username).first()

    if existing_user is None:
        register_new_user(user, db)
        print("Main user created.")
    else:
        print("Main user already exists.")

    db.close()


async def clear_db_img(db: Session):
    images_folder = "static/images"
    if os.path.exists(images_folder):
        shutil.rmtree(images_folder)
        print(f"Folder {images_folder} deleted.")
    else:
        print(f"Folder {images_folder} does not exist.")

    db.execute(text("DELETE FROM order_product"))
    db.query(Order).delete()
    db.query(Product).delete()
    db.query(Category).delete()
    db.query(Supplier).delete()
    db.commit()
    print("Database cleared")


async def seed():
    start_time = time.time()
    db = SessionLocal()
    try:
        await clear_db_img(db)
        await seed_suppliers(db, 50)
        await seed_categories(db, 10)
        # Use new seeder with real images from internet
        await seed_products_from_internet(db, 100)
        # await seed_orders(db, 50)
    finally:
        db.close()

    elapsed_time = time.time() - start_time
    print(f"Seeding completed in {elapsed_time:.2f} seconds")


if __name__ == "__main__":
    create_tables()
    # create_main_user()
    asyncio.run(seed())

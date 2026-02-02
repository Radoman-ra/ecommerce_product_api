from faker import Faker
from sqlalchemy.orm import Session
from tqdm.asyncio import tqdm
from ..tables import Product, Category, Supplier
from PIL import Image, ImageDraw
import os
import random
import numpy as np
import hashlib

fake = Faker()


def hash_filename(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def generate_gradient_image(
    file_name: str,
    base_folder: str,
    original_width: int = 1000,
    original_height: int = 1000,
):
    random_image = np.random.randint(
        0, 256, (original_height, original_width, 3), dtype=np.uint8
    )
    img = Image.fromarray(random_image)
    draw = ImageDraw.Draw(img)

    shape_size = random.randint(200, 500)
    shape_color = tuple(random.randint(0, 255) for _ in range(3))
    center_x, center_y = original_width // 2, original_height // 2

    shape_type = random.choice(["circle", "square", "triangle"])
    if shape_type == "circle":
        draw.ellipse(
            [
                (center_x - shape_size // 2, center_y - shape_size // 2),
                (center_x + shape_size // 2, center_y + shape_size // 2),
            ],
            fill=shape_color,
        )
    elif shape_type == "square":
        draw.rectangle(
            [
                (center_x - shape_size // 2, center_y - shape_size // 2),
                (center_x + shape_size // 2, center_y + shape_size // 2),
            ],
            fill=shape_color,
        )
    elif shape_type == "triangle":
        points = [
            (center_x, center_y - shape_size // 2),
            (center_x - shape_size // 2, center_y + shape_size // 2),
            (center_x + shape_size // 2, center_y + shape_size // 2),
        ]
        draw.polygon(points, fill=shape_color)

    sizes = [(500, 500), (100, 100), (1000, 1000), (10, 10)]

    for size in sizes:
        size_folder = os.path.join(base_folder, f"{size[0]}x{size[1]}")
        os.makedirs(size_folder, exist_ok=True)

        resized_img = img.resize(size, Image.Resampling.LANCZOS)

        resized_img.save(os.path.join(size_folder, f"{file_name}.png"), format="PNG")


async def seed_products(db: Session, num_products: int, batch_size: int = 1000):
    categories = db.query(Category).all()
    suppliers = db.query(Supplier).all()

    category_ids = [c.id for c in categories]
    supplier_ids = [s.id for s in suppliers]
    products_to_add = []

    name_count = {}

    async for _ in tqdm(range(num_products), desc="Seeding Products"):
        base_name = fake.word()

        if base_name in name_count:
            name_count[base_name] += 1
            product_name = f"{base_name}{name_count[base_name]}"
        else:
            name_count[base_name] = 1
            product_name = base_name

        hashed_name = hash_filename(product_name)
        photo_folder = f"static/images/"
        os.makedirs(photo_folder, exist_ok=True)

        generate_gradient_image(hashed_name, photo_folder)

        product = Product(
            name=product_name,
            description=fake.text(max_nb_chars=200),
            price=fake.random_number(digits=3),
            category_id=fake.random_element(elements=category_ids),
            supplier_id=fake.random_element(elements=supplier_ids),
            quantity=fake.random_number(digits=2),
            photo_path=f"{hashed_name}.png",
        )
        products_to_add.append(product)

        if len(products_to_add) >= batch_size:
            db.bulk_save_objects(products_to_add)
            db.commit()
            products_to_add = []

    if products_to_add:
        db.bulk_save_objects(products_to_add)
        db.commit()

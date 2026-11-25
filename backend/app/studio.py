"""The content area, where contributors edit the word graph."""

import re
import unicodedata
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .auth import Contributor, require_role
from .models import Category, Contribution, Link, User, Word
from .topics import Db

PAGE_SIZE = 50
MAX_BULK_WORDS = 200
WORD_MAX = 50
WORDS_PER_GROUP = 4
GRAPH_LOCK = 4444

router = APIRouter(
    prefix="/api/{topic_slug}/studio",
    tags=["studio"],
    dependencies=[Depends(require_role("contributor", "admin"))],
)


def clean(value: str) -> str:
    """Collapses whitespace and makes equivalent Unicode spellings identical."""
    value = re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()
    if any(unicodedata.category(c) == "Cc" for c in value):
        raise ValueError("contains characters that aren't allowed")
    return value


def clean_name(value: str) -> str:
    value = clean(value)
    if not value:
        raise ValueError("can't be blank")
    return value


def clean_optional(value: str | None) -> str | None:
    return None if value is None else value.replace("\0", "").strip() or None


WordText = Annotated[str, Field(max_length=WORD_MAX), AfterValidator(clean_name)]
CategoryName = Annotated[str, Field(max_length=256), AfterValidator(clean_name)]
LongText = Annotated[str | None, Field(max_length=2000), AfterValidator(clean_optional)]
Difficulty = Annotated[int, Field(ge=0, le=3)]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]
Search = Annotated[str, Query(max_length=256)]
Id = Annotated[int, Field(ge=1, le=2**31 - 1)]  # the range of a Postgres integer


# --- request and response shapes ---


class WordIn(BaseModel):
    text: WordText


class CategoryIn(BaseModel):
    name: CategoryName
    notes: LongText = None
    difficulty: Difficulty
    is_topical: bool


# In these, a field that's left out is unchanged. Defaults of None aren't
# validated, so sending null is still an error where the type doesn't allow it.
class CategoryPatch(BaseModel):
    name: CategoryName = None
    notes: LongText = None
    difficulty: Difficulty = None
    is_topical: bool = None


class LinkPatch(BaseModel):
    difficulty_override: Difficulty | None = None
    example_sentence: LongText = None


class LinkIn(BaseModel):
    word_id: Id
    category_id: Id


class BulkWordsIn(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_BULK_WORDS)


class BulkWordsOut(BaseModel):
    created: list[str]  # new words, now in the category
    linked: list[str]  # existing words, now in the category
    already_there: list[str]
    invalid: list[str]


class IdOut(BaseModel):
    id: int


class CategoryRef(BaseModel):
    id: int
    name: str
    is_topical: bool


class WordOut(BaseModel):
    id: int
    text: str
    is_topical: bool
    categories: list[CategoryRef]


class WordPage(BaseModel):
    total: int
    items: list[WordOut]


class CategoryOut(BaseModel):
    id: int
    name: str
    notes: str | None
    difficulty: int
    is_topical: bool
    word_count: int


class CategoryPage(BaseModel):
    total: int
    items: list[CategoryOut]


class CategoryWord(BaseModel):
    link_id: int
    word_id: int
    text: str
    meanings: int
    difficulty_override: int | None
    example_sentence: str | None


class CategoryDetail(CategoryOut):
    words: list[CategoryWord]


class WordCategory(BaseModel):
    link_id: int
    category_id: int
    name: str
    is_topical: bool
    difficulty: int
    difficulty_override: int | None
    example_sentence: str | None


class WordDetail(BaseModel):
    id: int
    text: str
    is_topical: bool
    categories: list[WordCategory]


class Summary(BaseModel):
    words: int
    categories: int
    links: int
    usable_categories: int
    categories_needing_words: int
    words_with_one_meaning: int


# --- helpers ---


def lock_graph(db: DbSession) -> None:
    """Lets one graph edit happen at a time, until the transaction ends. That's
    plenty for the number of editors, and rules out races between them."""
    db.execute(select(func.pg_advisory_xact_lock(GRAPH_LOCK)))


def record(db: DbSession, user: User, action: str, entity: Any, **details: Any) -> None:
    db.add(
        Contribution(
            user_id=user.id,
            action=action,
            entity_type={Word: "word", Category: "category", Link: "link"}[type(entity)],
            entity_id=entity.id,
            details=details or None,
        )
    )


def get_live(db: DbSession, model: Any, entity_id: int) -> Any:
    entity = db.scalar(select(model).where(model.id == entity_id, model.deleted_at.is_(None)))
    if entity is None:
        raise HTTPException(404, f"That {model.__name__.lower()} doesn't exist.")
    return entity


def find_named(db: DbSession, column: Any, value: str) -> Any:
    """The row with this name, ignoring case. Prefers a live row to a deleted one."""
    model = column.class_
    return db.scalar(
        select(model)
        .where(func.lower(column) == func.lower(value))
        .order_by(model.deleted_at.desc().nulls_first())
        .limit(1)
    )


def check_name_is_free(db: DbSession, column: Any, value: str, own_id: int | None = None) -> None:
    found = find_named(db, column, value)
    if found is not None and found.deleted_at is None and found.id != own_id:
        kind = column.class_.__name__.lower()
        raise HTTPException(409, f"There's already a {kind} called “{getattr(found, column.key)}”.")


def get_or_create_word(db: DbSession, user: User, value: str) -> tuple[Word, bool]:
    word = find_named(db, Word.text, value)
    if word is not None and word.deleted_at is None:
        return word, False
    if word is not None:
        word.deleted_at = None
        word.text = value
        record(db, user, "restore", word, text=value)
    else:
        word = Word(text=value)
        db.add(word)
        db.flush()
        record(db, user, "create", word, text=value)
    db.flush()
    return word, True


def get_or_create_link(
    db: DbSession, user: User, word_id: int, category_id: int
) -> tuple[Link, bool]:
    link = db.scalar(
        select(Link)
        .where(Link.word_id == word_id, Link.category_id == category_id)
        .order_by(Link.deleted_at.desc().nulls_first())
        .limit(1)
    )
    if link is not None and link.deleted_at is None:
        return link, False
    details = {"word_id": word_id, "category_id": category_id}
    if link is not None:
        link.deleted_at = None
        record(db, user, "restore", link, **details)
    else:
        link = Link(**details)
        db.add(link)
        db.flush()
        record(db, user, "create", link, **details)
    db.flush()
    return link, True


def apply_patch(db: DbSession, user: User, entity: Any, values: dict[str, Any]) -> None:
    changes = {}
    for field, new in values.items():
        old = getattr(entity, field)
        if old != new:
            changes[field] = {"from": old, "to": new}
            setattr(entity, field, new)
    if changes:
        record(db, user, "update", entity, **changes)


def soft_delete(db: DbSession, user: User, entity: Any) -> None:
    entity.deleted_at = datetime.now(UTC)
    record(db, user, "delete", entity)


def soft_delete_with_links(db: DbSession, user: User, entity: Word | Category) -> None:
    column = Link.word_id if isinstance(entity, Word) else Link.category_id
    for link in db.scalars(select(Link).where(column == entity.id, Link.deleted_at.is_(None))):
        soft_delete(db, user, link)
    soft_delete(db, user, entity)


def link_count(column: Any, entity_id: Any) -> Any:
    return (
        select(func.count())
        .select_from(Link)
        .where(column == entity_id, Link.deleted_at.is_(None))
        .scalar_subquery()
    )


def search_order(column: Any, search: str) -> list[Any]:
    """Best matches first when searching, otherwise newest first."""
    if not search:
        return [column.class_.id.desc()]
    return [
        (func.lower(column) == func.lower(search)).desc(),
        column.istartswith(search, autoescape=True).desc(),
        func.lower(column),
    ]


# --- overview ---


@router.get("/summary")
def summary(db: Db) -> Summary:
    def count(model: Any, *where: Any) -> int:
        return db.scalar(
            select(func.count()).select_from(model).where(model.deleted_at.is_(None), *where)
        )

    in_category = link_count(Link.category_id, Category.id)
    categories = count(Category)
    usable = count(Category, in_category >= WORDS_PER_GROUP)
    return Summary(
        words=count(Word),
        categories=categories,
        links=count(Link),
        usable_categories=usable,
        categories_needing_words=categories - usable,
        words_with_one_meaning=count(Word, link_count(Link.word_id, Word.id) == 1),
    )


# --- words ---


@router.get("/words")
def list_words(
    db: Db, search: Search = "", only: Literal["one_meaning"] | None = None, offset: Offset = 0
) -> WordPage:
    search = " ".join(search.replace("\0", "").split())
    where = [Word.deleted_at.is_(None)]
    if search:
        where.append(Word.text.icontains(search, autoescape=True))
    if only == "one_meaning":
        where.append(link_count(Link.word_id, Word.id) == 1)

    total = db.scalar(select(func.count()).select_from(Word).where(*where))
    words = db.scalars(
        select(Word)
        .where(*where)
        .order_by(*search_order(Word.text, search))
        .offset(offset)
        .limit(PAGE_SIZE)
    ).all()

    categories: dict[int, list[CategoryRef]] = {w.id: [] for w in words}
    for word_id, category in db.execute(
        select(Link.word_id, Category)
        .join(Category, Category.id == Link.category_id)
        .where(Link.word_id.in_(categories), Link.deleted_at.is_(None))
        .order_by(func.lower(Category.name))
    ):
        categories[word_id].append(
            CategoryRef(id=category.id, name=category.name, is_topical=category.is_topical)
        )
    return WordPage(
        total=total,
        items=[
            WordOut(
                id=w.id,
                text=w.text,
                is_topical=any(c.is_topical for c in categories[w.id]),
                categories=categories[w.id],
            )
            for w in words
        ],
    )


@router.post("/words", status_code=201)
def create_word(body: WordIn, db: Db, user: Contributor) -> IdOut:
    lock_graph(db)
    check_name_is_free(db, Word.text, body.text)
    word, _ = get_or_create_word(db, user, body.text)
    db.commit()
    return IdOut(id=word.id)


@router.get("/words/{word_id}")
def get_word(word_id: Id, db: Db) -> WordDetail:
    word = get_live(db, Word, word_id)
    rows = db.execute(
        select(Link, Category)
        .join(Category, Category.id == Link.category_id)
        .where(Link.word_id == word.id, Link.deleted_at.is_(None))
        .order_by(func.lower(Category.name))
    ).all()
    return WordDetail(
        id=word.id,
        text=word.text,
        is_topical=any(c.is_topical for _, c in rows),
        categories=[
            WordCategory(
                link_id=link.id,
                category_id=c.id,
                name=c.name,
                is_topical=c.is_topical,
                difficulty=c.difficulty,
                difficulty_override=link.difficulty_override,
                example_sentence=link.example_sentence,
            )
            for link, c in rows
        ],
    )


@router.patch("/words/{word_id}", status_code=204)
def update_word(word_id: Id, body: WordIn, db: Db, user: Contributor) -> None:
    lock_graph(db)
    word = get_live(db, Word, word_id)
    check_name_is_free(db, Word.text, body.text, word.id)
    apply_patch(db, user, word, body.model_dump())
    db.commit()


@router.delete("/words/{word_id}", status_code=204)
def delete_word(word_id: Id, db: Db, user: Contributor) -> None:
    lock_graph(db)
    soft_delete_with_links(db, user, get_live(db, Word, word_id))
    db.commit()


# --- categories ---


def category_out(category: Category, word_count: int) -> dict[str, Any]:
    return {
        "id": category.id,
        "name": category.name,
        "notes": category.notes,
        "difficulty": category.difficulty,
        "is_topical": category.is_topical,
        "word_count": word_count,
    }


@router.get("/categories")
def list_categories(
    db: Db,
    search: Search = "",
    only: Literal["needs_words", "topical", "not_topical"] | None = None,
    offset: Offset = 0,
) -> CategoryPage:
    search = " ".join(search.replace("\0", "").split())
    word_count = link_count(Link.category_id, Category.id)
    where = [Category.deleted_at.is_(None)]
    if search:
        where.append(Category.name.icontains(search, autoescape=True))
    if only == "needs_words":
        where.append(word_count < WORDS_PER_GROUP)
    elif only is not None:
        where.append(Category.is_topical.is_(only == "topical"))

    total = db.scalar(select(func.count()).select_from(Category).where(*where))
    rows = db.execute(
        select(Category, word_count)
        .where(*where)
        .order_by(*search_order(Category.name, search))
        .offset(offset)
        .limit(PAGE_SIZE)
    )
    return CategoryPage(total=total, items=[CategoryOut(**category_out(c, n)) for c, n in rows])


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, db: Db, user: Contributor) -> IdOut:
    lock_graph(db)
    check_name_is_free(db, Category.name, body.name)
    category = find_named(db, Category.name, body.name)
    if category is not None:
        category.deleted_at = None
        for field, value in body.model_dump().items():
            setattr(category, field, value)
        record(db, user, "restore", category, **body.model_dump())
    else:
        category = Category(**body.model_dump())
        db.add(category)
        db.flush()
        record(db, user, "create", category, **body.model_dump())
    db.commit()
    return IdOut(id=category.id)


@router.get("/categories/{category_id}")
def get_category(category_id: Id, db: Db) -> CategoryDetail:
    category = get_live(db, Category, category_id)
    rows = db.execute(
        select(Link, Word, link_count_of_word())
        .join(Word, Word.id == Link.word_id)
        .where(Link.category_id == category.id, Link.deleted_at.is_(None))
        .order_by(func.lower(Word.text))
    ).all()
    return CategoryDetail(
        **category_out(category, len(rows)),
        words=[
            CategoryWord(
                link_id=link.id,
                word_id=word.id,
                text=word.text,
                meanings=meanings,
                difficulty_override=link.difficulty_override,
                example_sentence=link.example_sentence,
            )
            for link, word, meanings in rows
        ],
    )


def link_count_of_word() -> Any:
    """Counts a word's links in a query that already joins one of them."""
    other = Link.__table__.alias("other_links")
    return (
        select(func.count())
        .select_from(other)
        .where(other.c.word_id == Word.id, other.c.deleted_at.is_(None))
        .correlate(Word)
        .scalar_subquery()
    )


@router.patch("/categories/{category_id}", status_code=204)
def update_category(category_id: Id, body: CategoryPatch, db: Db, user: Contributor) -> None:
    lock_graph(db)
    category = get_live(db, Category, category_id)
    values = body.model_dump(exclude_unset=True)
    if "name" in values:
        check_name_is_free(db, Category.name, values["name"], category.id)
    apply_patch(db, user, category, values)
    db.commit()


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: Id, db: Db, user: Contributor) -> None:
    lock_graph(db)
    soft_delete_with_links(db, user, get_live(db, Category, category_id))
    db.commit()


@router.post("/categories/{category_id}/words")
def add_words(category_id: Id, body: BulkWordsIn, db: Db, user: Contributor) -> BulkWordsOut:
    """Adds many words to a category, creating those that don't exist yet."""
    lock_graph(db)
    category = get_live(db, Category, category_id)
    result = BulkWordsOut(created=[], linked=[], already_there=[], invalid=[])
    done: set[int] = set()
    for raw in body.texts:
        try:
            value = clean(raw)
        except ValueError:
            result.invalid.append(raw[:100])
            continue
        if not value:
            continue
        if len(value) > WORD_MAX:
            result.invalid.append(value[:100])
            continue
        word, is_new = get_or_create_word(db, user, value)
        if word.id in done:
            continue
        done.add(word.id)
        _, link_is_new = get_or_create_link(db, user, word.id, category.id)
        if is_new:
            result.created.append(word.text)
        elif link_is_new:
            result.linked.append(word.text)
        else:
            result.already_there.append(word.text)
    db.commit()
    return result


# --- links ---


@router.post("/links", status_code=201)
def create_link(body: LinkIn, db: Db, user: Contributor) -> IdOut:
    lock_graph(db)
    word = get_live(db, Word, body.word_id)
    category = get_live(db, Category, body.category_id)
    link, is_new = get_or_create_link(db, user, word.id, category.id)
    if not is_new:
        raise HTTPException(409, f"“{word.text}” is already in “{category.name}”.")
    db.commit()
    return IdOut(id=link.id)


@router.patch("/links/{link_id}", status_code=204)
def update_link(link_id: Id, body: LinkPatch, db: Db, user: Contributor) -> None:
    lock_graph(db)
    apply_patch(db, user, get_live(db, Link, link_id), body.model_dump(exclude_unset=True))
    db.commit()


@router.delete("/links/{link_id}", status_code=204)
def delete_link(link_id: Id, db: Db, user: Contributor) -> None:
    lock_graph(db)
    soft_delete(db, user, get_live(db, Link, link_id))
    db.commit()

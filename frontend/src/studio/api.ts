import { call } from "../api";

export type CategoryRef = { id: number; name: string; is_topical: boolean };
export type Word = { id: number; text: string; is_topical: boolean; categories: CategoryRef[] };
export type Category = {
  id: number;
  name: string;
  notes: string | null;
  difficulty: number;
  is_topical: boolean;
  word_count: number;
};
export type CategoryFields = Pick<Category, "name" | "notes" | "difficulty" | "is_topical">;
export type LinkFields = { difficulty_override: number | null; example_sentence: string | null };
export type CategoryWord = LinkFields & {
  link_id: number;
  word_id: number;
  text: string;
  meanings: number;
};
export type CategoryDetail = Category & { words: CategoryWord[] };
export type WordCategory = LinkFields & {
  link_id: number;
  category_id: number;
  name: string;
  is_topical: boolean;
  difficulty: number;
};
export type WordDetail = {
  id: number;
  text: string;
  is_topical: boolean;
  categories: WordCategory[];
};
export type Page<T> = { total: number; items: T[] };
export type Summary = {
  words: number;
  categories: number;
  links: number;
  usable_categories: number;
  categories_needing_words: number;
  words_with_one_meaning: number;
};
export type BulkResult = Record<"created" | "linked" | "already_there" | "invalid", string[]>;
type Created = { id: number };
export type ListParams = { search?: string; only?: string; offset?: number };

export const DIFFICULTIES = ["Easy", "Medium", "Hard", "Very hard"];
export const MAX_BULK_WORDS = 200;
export const MAX_WORD_LENGTH = 50;

function query({ search, only, offset }: ListParams): string {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (only) params.set("only", only);
  if (offset) params.set("offset", String(offset));
  return `?${params}`;
}

export const studio = {
  summary: () => call<Summary>("GET", "/studio/summary"),

  words: (params: ListParams) => call<Page<Word>>("GET", `/studio/words${query(params)}`),
  word: (id: number) => call<WordDetail>("GET", `/studio/words/${id}`),
  createWord: (text: string) => call<Created>("POST", "/studio/words", { text }),
  updateWord: (id: number, text: string) => call<void>("PATCH", `/studio/words/${id}`, { text }),
  deleteWord: (id: number) => call<void>("DELETE", `/studio/words/${id}`),

  categories: (params: ListParams) =>
    call<Page<Category>>("GET", `/studio/categories${query(params)}`),
  category: (id: number) => call<CategoryDetail>("GET", `/studio/categories/${id}`),
  createCategory: (fields: CategoryFields) => call<Created>("POST", "/studio/categories", fields),
  updateCategory: (id: number, fields: Partial<CategoryFields>) =>
    call<void>("PATCH", `/studio/categories/${id}`, fields),
  deleteCategory: (id: number) => call<void>("DELETE", `/studio/categories/${id}`),
  addWords: (id: number, texts: string[]) =>
    call<BulkResult>("POST", `/studio/categories/${id}/words`, { texts }),

  createLink: (word_id: number, category_id: number) =>
    call<Created>("POST", "/studio/links", { word_id, category_id }),
  updateLink: (id: number, fields: Partial<LinkFields>) =>
    call<void>("PATCH", `/studio/links/${id}`, fields),
  deleteLink: (id: number) => call<void>("DELETE", `/studio/links/${id}`),
};

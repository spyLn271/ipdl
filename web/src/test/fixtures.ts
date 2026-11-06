import methodologyJson from "@/mocks/methodology.json";
import personJson from "@/mocks/person-detail.json";
import { methodologySchema, personDetailSchema } from "@/lib/api/schemas";

/** Ответы API для тестов: вымышленный портрет (сценарий tests/sample.py бэкенда), методика — настоящая. */
export const personDetail = personDetailSchema.parse(personJson);
export const portraitOut = personDetail.current!;
export const portrait = portraitOut.portrait!;
export const methodology = methodologySchema.parse(methodologyJson);

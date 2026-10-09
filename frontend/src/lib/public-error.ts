/** Historical agent messages may contain the collection supplier's name. */
export function publicError(message: unknown) {
  return String(message).replace(/xml\s*r(?:iver|eaver)/gi, "Сервис сбора")
}

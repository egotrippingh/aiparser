/** Historical agent messages may contain the collection supplier's name. */
export function publicError(message: string) {
  return message.replace(/xml\s*ri(?:ver|aver)/gi, "Сервис сбора")
}

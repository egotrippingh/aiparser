import { StrictMode } from "react"
import { renderToStaticMarkup, renderToString } from "react-dom/server"
import { HelpPage } from "./help-page"
import { helpHref, type HelpArticle } from "./help-content"

export function renderHelpPage(article: HelpArticle) {
  return renderToString(<StrictMode><HelpPage article={article} /></StrictMode>)
}

export function renderHelpHead(article: HelpArticle) {
  const title = `${article.title} — AIRate`
  const canonical = `https://airate.tech${helpHref(article)}`
  return renderToStaticMarkup(<>
    <title>{title}</title>
    <meta name="description" content={article.summary} />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href={canonical} />
    <meta property="og:type" content="article" />
    <meta property="og:locale" content="ru_RU" />
    <meta property="og:title" content={title} />
    <meta property="og:description" content={article.summary} />
    <meta property="og:url" content={canonical} />
  </>)
}

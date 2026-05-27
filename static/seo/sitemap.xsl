<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9">
  <xsl:output method="html" indent="yes" encoding="UTF-8"/>
  <xsl:template match="/">
    <html lang="az">
      <head>
        <meta charset="UTF-8"/>
        <title>EMSArena – Sayt xəritəsi</title>
        <meta name="robots" content="noindex"/>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                 background: #f8fafc; color: #0f172a; margin: 0; padding: 32px 16px; }
          .wrap { max-width: 1100px; margin: 0 auto; }
          h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: -0.02em;
               background: linear-gradient(135deg,#1e40af,#0f766e,#10b981);
               -webkit-background-clip: text; background-clip: text; color: transparent; }
          p { color: #475569; margin: 0 0 24px; }
          table { width: 100%; border-collapse: collapse;
                  background: #fff; border-radius: 14px; overflow: hidden;
                  box-shadow: 0 10px 28px rgba(15,23,42,0.06); }
          th { text-align: left; padding: 14px 18px; background: #f1f5f9;
               font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: #475569;}
          td { padding: 12px 18px; border-top: 1px solid #e2e8f0; font-size: 14px; }
          td a { color: #1e40af; text-decoration: none; font-weight: 600; }
          td a:hover { text-decoration: underline; }
          .pill { display: inline-block; padding: 2px 10px; border-radius: 999px;
                  background: rgba(15,118,110,0.08); color: #0f766e;
                  font-size: 12px; font-weight: 600; }
        </style>
      </head>
      <body>
        <div class="wrap">
          <h1>EMSArena – Sayt xəritəsi</h1>
          <p>Bu səhifə axtarış sistemləri üçündür. Cəmi <strong><xsl:value-of select="count(sm:urlset/sm:url)"/></strong> URL siyahıda.</p>
          <table>
            <thead>
              <tr><th>URL</th><th>Son dəyişiklik</th><th>Tezlik</th><th>Prioritet</th></tr>
            </thead>
            <tbody>
              <xsl:for-each select="sm:urlset/sm:url">
                <tr>
                  <td><a href="{sm:loc}"><xsl:value-of select="sm:loc"/></a></td>
                  <td><xsl:value-of select="sm:lastmod"/></td>
                  <td><span class="pill"><xsl:value-of select="sm:changefreq"/></span></td>
                  <td><xsl:value-of select="sm:priority"/></td>
                </tr>
              </xsl:for-each>
            </tbody>
          </table>
        </div>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>

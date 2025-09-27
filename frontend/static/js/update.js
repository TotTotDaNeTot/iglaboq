export default async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.redirect(302, `/shop.html?t=${Date.now()}&${req.query.journal ? 'journal=' + req.query.journal : ''}`);
}
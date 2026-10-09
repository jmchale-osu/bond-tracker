from edgar import set_identity, Company

set_identity("James McHale jtmchale912@gmail.com")

filings = Company(895126).get_filings(form=["FWP", "424B5"])
print(filings.latest(5))

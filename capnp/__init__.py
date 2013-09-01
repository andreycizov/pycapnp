"""A python library wrapping the Cap'n Proto C++ library

Example Usage::
    
    import capnp

    addressbook = capnp.load('addressbook.capnp')

    # Building
    addresses = addressbook.AddressBook.newMessage()
    people = addresses.init('people', 1)

    alice = people[0]
    alice.id = 123
    alice.name = 'Alice'
    alice.email = 'alice@example.com'
    alicePhone = alice.init('phones', 1)[0]
    alicePhone.type = 'mobile'

    f = open('example.bin', 'w')
    addresses.writeTo(f)
    f.close()

    # Reading
    f = open('example.bin')

    addresses = addressbook.AddressBook.readFrom(f)

    for person in addresses.people:
        print(person.name, ':', person.email)
        for phone in person.phones:
            print(phone.type, ':', phone.number)
"""
from .version import version as __version__
from .capnp import *
from .capnp import _DynamicStructReader, _DynamicStructBuilder, _DynamicResizableListBuilder, _DynamicListReader, _DynamicListBuilder, _DynamicOrphan, _DynamicResizableListBuilder
del capnp
